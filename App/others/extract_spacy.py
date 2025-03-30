from flask import Flask, request, jsonify
import boto3
import spacy
from spacy import displacy

app = Flask(__name__)

# Configurações do AWS
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')

# Carregar modelo do Spacy para português
nlp = spacy.load("pt_core_news_sm")

#carregamento da imagem para o bucket s3
def upload_to_s3(file_path, bucket_name, object_name):
    try:
        s3_client.upload_file(file_path, bucket_name, object_name)
        return True
    except Exception as e:
        print(f"Erro ao enviar arquivo para o S3: {e}")
        return False

#extração de texto da imagem com textract
def extract_text_from_image(bucket_name, object_name):
    try:
        response = textract_client.detect_document_text(
            Document={'S3Object': {'Bucket': bucket_name, 'Name': object_name}}
        )
        text = ""
        for item in response['Blocks']:
            if item['BlockType'] == "LINE":
                text += item['Text'] + "\n"
        return text
    except Exception as e:
        print(f"Erro ao extrair texto com Textract: {e}")
        return None

#extração de informações da nota fiscal com spacy e regex
def extract_invoice_info_spacy(text):
    doc = nlp(text)
    invoice_info = {
        "nome_emissor": None,
        "CNPJ_emissor": None,
        "endereco_emissor": None,
        "CNPJ_CPF_consumidor": None,
        "data_emissao": None,
        "numero_nota_fiscal": None,
        "serie_nota_fiscal": None,
        "valor_total": None,
        "forma_pgto": None
    }

    return invoice_info

@app.route('/api/v1/invoice', methods=['POST'])
def process_invoice():
    files = request.files.getlist('file')
    if not files or len(files) == 0:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    # Nome do bucket S3
    bucket_name = "testandocriarbuckernomeusss"
    responses = []
    final = []

    # Processamento de cada arquivo enviado 
    for file in files:
        if file.filename == '':
            responses.append({"error": "Nome do arquivo inválido"})
            continue

        # Salvar o arquivo temporariamente
        file_path = f"temp_{file.filename}"
        file.save(file_path)

        # Enviar para o S3
        object_name = file.filename
        if not upload_to_s3(file_path, bucket_name, object_name):
            responses.append({"error": f"Falha ao enviar o arquivo {file.filename} para o S3"})
            continue

        # Extrair texto com Textract
        extracted_text = extract_text_from_image(bucket_name, object_name)
        if not extracted_text:
            responses.append({"error": f"Falha ao extrair texto do arquivo {file.filename}"})
        else:
            responses.append(extracted_text)

    for responses in responses:
        texto_tratado = responses.replace('\n', ' ')
        invoice_info = extract_invoice_info_spacy(texto_tratado)
        final.append(invoice_info)

    return jsonify(final)

if __name__ == '__main__':
    app.run(debug=True)