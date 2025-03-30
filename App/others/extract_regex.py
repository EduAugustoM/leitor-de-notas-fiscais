from flask import Flask, request, jsonify
import boto3
import spacy
from spacy import displacy
import re
import unicodedata

app = Flask(__name__)

# Configurações do AWS
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')

# Carregar modelo do Spacy para português
nlp = spacy.load("pt_core_news_lg")

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

    # Extração de nomes de empresas
    nome_pattern = re.compile(r'(.+?)\s+(LTDA|LIDA|Ltds|Ltda|S\.A\.|EIRELI|- ME)\b', re.IGNORECASE)
    nome_match = nome_pattern.search(doc.text)
    if nome_match:
        invoice_info["nome_emissor"] = nome_match.group()

    # Padrão para CNPJ (ex.: 12.345.678/0001-12)
    cnpj_pattern = re.compile(r'''
        (\d{2}[\.\s_]?\d{3}[\.\s_]?\d{3}[\.\s_/]?\d{4}[\.\s_-]?\d{2})  # XX.XXX.XXX/XXXX-XX com variações de separadores
        | (\d{14})  # CNPJ contínuo sem formatação
    ''', re.VERBOSE)
    cnpj_match = cnpj_pattern.search(doc.text)
    if cnpj_match:
        invoice_info["CNPJ_emissor"] = cnpj_match.group()

    # Padrão para endereços
    endereco_pattern = re.compile(r'''
        (RUA|ALAMEDA|TRECHO|AU|AV|Rua|AVENIDA|ROD|RODOVIA|RUR|Ave)  # Prefixos do endereço
        [\s,.-]+  # Separadores comuns (espaço, vírgula, ponto, hífen)
        ([\w\s,.-]+)  # Restante do endereço (pode incluir letras, números, espaços, vírgulas, pontos, hífens)
    ''', re.VERBOSE | re.IGNORECASE)
    endereco_match = endereco_pattern.search(doc.text)
    if endereco_match:
        endereco_completo = endereco_match.group()  # Captura o endereço completo
        endereco_truncado = endereco_completo[:70]
        invoice_info["endereco_emissor"] = endereco_truncado.strip()

    # Padrão para CPF (ex.: 123.456.789-09, 123 456 789 09, 12345678909)
    cpf_pattern = re.compile(r'''
        (?<!\S)  # Verifica se não há um caractere não-espaço antes (ou seja, espaço ou início do texto)
        (
            \d{3}[\.\s-]?\d{3}[\.\s-]?\d{3}[\.\s-]?\d{2}  # CPF formatado (123.456.789-09, 123 456 789 09, etc.)
            | \d{11}  # CPF sem formatação (19044690868)
            | nao\s*identificado  # "nao identificado"
            | não\s*informado  # "não informado"
            | NAO\s*IDENTIFICADO  # "NAO IDENTIFICADO"
        )
        (?!\S)  # Verifica se não há um caractere não-espaço depois (ou seja, espaço ou fim do texto)
    ''', re.VERBOSE | re.IGNORECASE)
    cpf_match = cpf_pattern.search(doc.text)
    if cpf_match:
        invoice_info["CNPJ_CPF_consumidor"] = cpf_match.group()

    # Padrão para data de emissão no formato DD/MM/AAAA
    date_pattern = re.compile(r'\d{2}/\d{2}/\d{4}')
    date_match = date_pattern.search(text)
    if date_match:
        invoice_info["data_emissao"] = date_match.group()

    # Regex para capturar números de 9 dígitos que começam com 000 (formatados ou não)
    nota_pattern_nove_digitos = re.compile(r'''
        (
            000[\.\s-]?\d{3}[\.\s-]?\d{3}  # Números formatados (000.650.509, 000 650 509, etc.)
            | 000\d{6}  # Números não formatados (000000139)
        )
        (?!\S)  # Lookahead negativo para espaços ou fim do texto
    ''', re.VERBOSE)
    # Regex para capturar números de 6 dígitos isolados
    nota_pattern_seis_digitos = re.compile(r'''
        (?<!\d)  # Lookbehind negativo: garante que não há um dígito antes
        (\d{6})  # Captura exatamente 6 dígitos
        (?!\d)   # Lookahead negativo: garante que não há um dígito depois
    ''', re.VERBOSE)
    # Tenta capturar o número de 9 dígitos primeiro
    nota_match = nota_pattern_nove_digitos.search(doc.text)
    if nota_match:
        numero_nota = nota_match.group(1).replace(".", "").replace(" ", "").replace("-", "")  # Remove formatação
        invoice_info["numero_nota_fiscal"] = numero_nota
    else:
        # Se não encontrar um número de 9 dígitos, tenta capturar o número de 6 dígitos
        nota_match = nota_pattern_seis_digitos.search(doc.text)
        if nota_match:
            invoice_info["numero_nota_fiscal"] = nota_match.group(1)

    # Extração da série da nota fiscal
    serie_pattern = re.compile(r'''
        (Serie | Série | serie | série)\s*  # Palavra "Serie" (pode ter espaços após)
        [:\-]?\s*  # Separador opcional (dois pontos ou hífen, seguido de espaços opcionais)
        (\d{1,3})  # Captura números com 1 a 3 dígitos
    ''', re.VERBOSE | re.IGNORECASE)
    serie_match = serie_pattern.search(text)
    if serie_match:
        invoice_info["serie_nota_fiscal"] = serie_match.group(2)

    # Extração do valor total (considerando diversas variações)
    valor_pattern = re.compile(r'''
        (?:Total|Valor\s+Total|TOTAL)  # Prefixos (Total, Valor Total)
        \s*  # Espaços opcionais
        [:\-]?\s*  # Separadores opcionais (dois pontos, hífen, espaços)
        (?:R\$|RS)?\s*  # Símbolo monetário opcional (R$, RS)
        (\d{1,3}(?:[\s,.]?\d{3})*(?:[.,]\d{2}))  # Valor monetário (com formatação variada)
    ''', re.VERBOSE | re.IGNORECASE)
    valor_match = valor_pattern.search(text)
    if valor_match:
        valor_total = valor_match.group(1)
        invoice_info["valor_total"] = valor_total

    # Extração da forma de pagamento por meio de palavras-chave
    lower_text = text.lower()
    if "dinheiro" in lower_text:
        invoice_info["forma_pgto"] = "Dinheiro"
    else:
        invoice_info["forma_pgto"] = "Cartão"

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
        # invoice_info = extract_invoice_info_spacy(texto_tratado)
        final.append(texto_tratado)

    return jsonify(final)

if __name__ == '__main__':
    app.run(debug=True)