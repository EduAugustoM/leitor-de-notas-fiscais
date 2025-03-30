from flask import Flask, request, jsonify
import boto3
from transformers import pipeline

app = Flask(__name__)

# Configurações do AWS
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')

# Carregar modelo do Transformers para Q&A
qea = pipeline("question-answering", model="pierreguillou/bert-base-cased-squad-v1.1-portuguese")

# Função para extrair o texto da imagem com Textract
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

# Função para extrair informações da nota fiscal com pipeline de Q&A
def extract_invoice_info_transf(text):
    questions = [
        "Qual o nome do emissor?",
        "Qual o CNPJ do emissor?",
        "Qual o endereço do emissor?",
        "Qual o CPF do consumidor?",
        "Qual a data de emissão?",
        "Qual o número da nota fiscal?",
        "Qual a série da nota fiscal?",
        "Qual o valor total?",
        "Qual a forma de pagamento?"
    ]
    answers = qea(question=questions, context=text)
    invoice_info = {
        "nome_emissor": answers[0]["answer"],
        "CNPJ_emissor": answers[1]["answer"],
        "endereco_emissor": answers[2]["answer"],
        "CNPJ_CPF_consumidor": answers[3]["answer"],
        "data_emissao": answers[4]["answer"],
        "numero_nota_fiscal": answers[5]["answer"],
        "serie_nota_fiscal": answers[6]["answer"],
        "valor_total": answers[7]["answer"],
        "forma_pgto": answers[8]["answer"]
    }
    return invoice_info


@app.route('/api/v1/invoice', methods=['POST'])
def process_invoice():
    files = request.files.getlist('file')
    if not files:
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

        # Considera que o objeto já está no bucket com esse nome.
        object_name = file.filename

        # Extração do texto com Textract
        extracted_text = extract_text_from_image(bucket_name, object_name)
        if not extracted_text:
            responses.append(
                {"error": f"Falha ao extrair texto do arquivo {file.filename}"})
        else:
            responses.append(extracted_text)

    # Extração das informações da nota fiscal com Transformers
    for responses in responses:
        texto_tratado = responses.replace('\n', ' ')
        invoice_info = extract_invoice_info_transf(texto_tratado)
        final.append(invoice_info)

    return jsonify(final)

if __name__ == '__main__':
    app.run(debug=True)
