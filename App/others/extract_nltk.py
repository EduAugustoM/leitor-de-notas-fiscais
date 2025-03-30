import json
import re
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.tag import pos_tag

nltk.download("stopwords")
nltk.download("punkt")
nltk.download('punkt_tab')
nltk.download("averaged_perceptron_tagger")
nltk.download('averaged_perceptron_tagger_eng')

def preprocess_text(text):
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"[^\w\s.,/-]", "", text)

def tokenize_and_tag(text):
    tokens = word_tokenize(text, language="portuguese")
    stop_words = set(stopwords.words("portuguese"))
    custom_stopwords = {'valor', 'r$', 'item', 'un', 'kg', 'ml', 'cx', 'pt', 'codigo', 'descricao'}
    filtered_tokens = [
        t for t in tokens 
        if t.lower() not in stop_words and 
           t.lower() not in custom_stopwords and
           (len(t) > 1 or t.isdigit())
    ]
    return pos_tag(filtered_tokens)

def extract_emissor_info(tokens):
    cnpj_pattern = r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"
    nome, endereco = None, []
    in_address = False
    address_keywords = {'SCES', 'RUA', 'AV', 'ROD', 'ALAMEDA', 'TRAVESSA', 
                      'AL', 'QD', 'QUADRA', 'CONJ', 'LOJA', 'BAIRRO', 'CEP'}
    
    for i, (token, tag) in enumerate(tokens):
        # Extração do nome do emissor
        if re.fullmatch(cnpj_pattern, token):
            nome_tokens = []
            for j in range(i+1, len(tokens)):
                if tokens[j][0] in address_keywords or tokens[j][0].isdigit():
                    break
                if tokens[j][1] in ('NNP', 'NN', 'NNS', 'JJ'):
                    nome_tokens.append(tokens[j][0])
            nome = ' '.join(nome_tokens) if nome_tokens else None
        
        # Detecção de endereço
        if token in address_keywords:
            in_address = True
        if in_address:
            endereco.append(token)
            if re.match(r"\d{5}-?\d{3}", token):
                break
            if len(endereco) > 15:  # Limite máximo para endereço
                break
    
    return nome, ' '.join(endereco) if endereco else None

def extract_forma_pagamento(tokens):
    payment_keywords = {
        'débito': 'Débito',
        'crédito': 'Crédito',
        'credito': 'Crédito',
        'debito': 'Débito',
        'dinheiro': 'Dinheiro',
        'pix': 'Pix',
        'cartão': 'Cartão',
        'cartao': 'Cartão'
    }
    
    for i, (token, tag) in enumerate(tokens):
        if token.lower() == 'pagamento' and i > 0 and tokens[i-1][0].lower() == 'forma':
            payment_phrase = []
            for j in range(i+1, len(tokens)):
                if re.match(r"^\d+[,.]\d{2}$", tokens[j][0]):
                    break
                payment_phrase.append(tokens[j][0].lower())
            
            # Verifica combinações compostas
            joined_phrase = ' '.join(payment_phrase)
            for key in payment_keywords:
                if key in joined_phrase:
                    return payment_keywords[key]
            
            # Verifica palavras-chave individuais
            for word in payment_phrase:
                if word in payment_keywords:
                    return payment_keywords[word]
            
            # Caso especial para cartões
            if 'cart' in joined_phrase:
                if 'débit' in joined_phrase or 'debit' in joined_phrase:
                    return 'Débito'
                if 'crédit' in joined_phrase or 'credit' in joined_phrase:
                    return 'Crédito'
                return 'Cartão'
    
    return 'Outros'

def extract_numeros_nota(tokens):
    nf, serie = None, None
    nf_patterns = {'nfc-e', 'mfc-e', 'nfce', 'nf-e', 'cupom', 'nota'}
    
    for i, (token, tag) in enumerate(tokens):
        token_lower = token.lower()
        if token_lower in nf_patterns:
            # Procura número após o padrão
            for j in range(i+1, min(i+4, len(tokens))):
                clean_num = tokens[j][0].replace('.', '').replace('-', '')
                if re.fullmatch(r"\d{9}", clean_num):
                    nf = clean_num
                    break
        if token_lower == 'série' and i+1 < len(tokens):
            serie = tokens[i+1][0]
    
    return nf, serie

def extract_data_emissao(tokens):
    for token, tag in tokens:
        if re.match(r"\d{2}/\d{2}/\d{4}", token):
            return token
    return None

def extract_valores(tokens):
    valores = [t[0] for t in reversed(tokens) if re.match(r"^\d+[,.]\d{2}$", t[0])]
    total = None
    if valores:
        total = valores[0].replace('.', ',')
    return total

def process_nota_fiscal(text):
    text = preprocess_text(text)
    tokens = tokenize_and_tag(text)
    
    nome_emissor, endereco = extract_emissor_info(tokens)
    
    return {
        "nome_emissor": nome_emissor,
        "CNPJ_emissor": next((t[0] for t in tokens if re.match(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", t[0])), None),
        "endereco_emissor": endereco,
        "CNPJ_CPF_consumidor": next((t[0] for t in tokens if re.match(r"\d{3}\.\d{3}\.\d{3}-\d{2}", t[0])), None),
        "data_emissao": extract_data_emissao(tokens),
        "numero_nota_fiscal": extract_numeros_nota(tokens)[0],
        "serie_nota_fiscal": extract_numeros_nota(tokens)[1],
        "valor_total": extract_valores(tokens),
        "forma_pgto": extract_forma_pagamento(tokens),
    }

def processar_arquivo_json(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        dados_textract = json.load(f)
    
    resultados = {}
    
    for arquivo, conteudo in dados_textract.items():
        try:
            texto = ' '.join(conteudo['textos_extraidos'])
            resultados[arquivo] = process_nota_fiscal(texto)
        except Exception as e:
            resultados[arquivo] = {"erro": f"Falha no processamento: {str(e)}"}
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(resultados, f, ensure_ascii=False, indent=4)
    
    print(f"Processamento concluído! Resultados salvos em {output_file}")

if __name__ == "__main__":
    processar_arquivo_json('resultados_textract.json', 'resultados_processados.json')