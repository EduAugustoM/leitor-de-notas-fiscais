from flask import Flask, request, jsonify
import boto3
from transformers import pipeline
import logging

app = Flask(__name__)

# Configurações do AWS
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')

# Configurar logging para melhor depuração
logging.basicConfig(level=logging.INFO)

# Carregar modelo DeepSeek com pipeline de question-answering
qa_pipe = pipeline(
    "question-answering",
    model="pierreguillou/bert-large-cased-squad-v1.1-portuguese",
    device="cuda"  # Certifique-se de que a GPU esteja disponível ou ajuste para "cpu"
)

# Função para formatar prompts específicos (opcional, mas pode ajudar a orientar melhor o modelo)
def format_prompt(context, question):
    # Sugestão: incluir instruções que reforcem a objetividade e a estrutura da resposta
    prompt = (
        f"Você recebeu o seguinte texto extraído de uma nota fiscal:\n\n"
        f"{context}\n\n"
        f"Com base nesse texto, responda objetivamente a seguinte pergunta:\n"
        f"{question}\n\n"
        f"Responda com clareza e de forma resumida."
    )
    return prompt

# Função para extrair o texto da imagem com Textract
def extract_text_from_image(bucket_name, object_name):
    try:
        response = textract_client.detect_document_text(
            Document={'S3Object': {'Bucket': bucket_name, 'Name': object_name}}
        )
        text = ""
        for item in response.get('Blocks', []):
            if item.get('BlockType') == "LINE":
                text += item.get('Text', '') + "\n"
        return text
    except Exception as e:
        logging.error(f"Erro ao extrair texto com Textract: {e}")
        return None

# Função para extrair informações da nota fiscal utilizando Transformers
def extract_invoice_info(text):
    questions = [
        "Qual o nome do emissor? geralmente esse nome esta associado a razão social, LTDA, S/A, ME, EIRELI, etc",
        "Qual o CNPJ do emissor? ele possui 14 dígitos formatados (12.345.678/0001-12) ou não formatados (12345678000112) podendo conter espaços ou simbolos entre os numeros", 
        "Qual o endereço do emissor? em texto vem acompanhado de Rua, Alameda, Avenida, Rodovia ou abreviados como R., Av., Al., etc",
        "Qual o CPF do consumidor? ele possui 11 dígitos formatados (123.456.789-00) ou não formatados (12345678900) podendo conter espaços ou simbolos entre os numeros. no texto ele encontra-se junto de 'consumidor' ou 'CPF' e se não encontrar retorne null",
        "Qual a data de emissão? ela possui o formato DD/MM/AAAA ou DD-MM-AAAA",
        "Qual o número da nota fiscal? geralmente são números inteiros de nove dígitos (000000123 que começam com 000 formatados ou não) ou seis dígitos isolados acompanhados do SAT",	
        "Qual a série da nota fiscal? geralmente são números inteiros 1,2,3 ou de três dígitos (101, 002, 003, etc) vindo logo após série no texto",
        "Qual o valor total? o valor total refere-se ao valor total da nota fiscal, podendo ser formatado com vírgula ou ponto (R$ 1.000,00 ou R$ 1000.00) e acompanhado de R$ sendo o maior valor da nota",
        "Qual a forma de pagamento? geralmente é dinheiro ou cartão"
    ]

    keys = [
        "nome_emissor", "CNPJ_emissor", "endereco_emissor",
        "CNPJ_CPF_consumidor", "data_emissao", "numero_nota_fiscal",
        "serie_nota_fiscal", "valor_total", "forma_pgto"
    ]

    # Criar inputs para batch
    inputs = [{"question": question, "context": text} for question in questions]

    # Rodar todas de uma vez
    respostas = qa_pipe(inputs)

    # Montar o dicionário de resposta
    invoice_data = {key: resposta.get("answer", "").strip() for key, resposta in zip(keys, respostas)}

    return invoice_data

@app.route('/api/v1/invoice', methods=['POST'])
def process_invoice():
    files = request.files.getlist('file')
    if not files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    bucket_name = "testandocriarbuckernomeusss"
    final_results = []

    # Processamento de cada arquivo enviado
    for file in files:
        if file.filename == '':
            logging.warning("Nome do arquivo inválido")
            continue

        # Se o arquivo não estiver no bucket, você pode considerar fazer upload aqui.
        object_name = file.filename

        # Extração do texto com Textract
        extracted_text = extract_text_from_image(bucket_name, object_name)
        if not extracted_text:
            logging.error(f"Falha ao extrair texto do arquivo {file.filename}")
            continue

        # Pré-processamento: substitui quebras de linha por espaços para facilitar a análise
        texto_tratado = extracted_text.replace('\n', ' ').strip()

        # Extração das informações da nota fiscal
        invoice_info = extract_invoice_info(texto_tratado)
        final_results.append({
            "arquivo": file.filename,
            "informacoes_nota": invoice_info
        })

    if not final_results:
        return jsonify({"error": "Nenhum arquivo processado com sucesso"}), 400

    return jsonify(final_results), 200

if __name__ == '__main__':
    app.run(debug=True)