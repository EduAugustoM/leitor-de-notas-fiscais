from flask import Flask, request, jsonify, render_template
import boto3
import logging
import os
import json
from dotenv import load_dotenv
import google.generativeai as genai

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# Configurações do AWS
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')

# Configurar logging
logging.basicConfig(level=logging.INFO)

# Configurar Gemini
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
gemini_model = genai.GenerativeModel('gemini-1.5-pro-latest')

def format_gemini_prompt(context):
    return f"""
    Analise este texto extraído de uma nota fiscal e extraia as seguintes informações em formato JSON.
    Retorne APENAS o JSON sem comentários ou formatação adicional. Use null para campos não encontrados.

    Texto:
    {context}

    Campos requeridos:
    - nome_emissor: Nome completo do emissor com razão social
    - CNPJ_emissor: CNPJ com 14 dígitos (formatado ou não)
    - endereco_emissor: Endereço completo com tipo de logradouro
    - CNPJ_CPF_consumidor: São os números do CPF de um consumidor se mencionado
    - data_emissao: Data em DD/MM/AAAA ou DD-MM-AAAA
    - numero_nota_fiscal: Número geralmente com 6-9 dígitos
    - serie_nota_fiscal: Série (1, 101, etc)
    - valor_total: Maior valor em R$ 
    - forma_pgto: Forma de pagamento (Dinheiro, Cartão, etc)
    """

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

def extract_invoice_info(text):
    try:
        prompt = format_gemini_prompt(text)
        response = gemini_model.generate_content(prompt)
        
        # Extrair conteúdo JSON da resposta
        json_str = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(json_str)
        
    except Exception as e:
        logging.error(f"Erro no Gemini: {e}")
        return {
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

@app.route('/')
def home():
    return render_template('index.html')

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