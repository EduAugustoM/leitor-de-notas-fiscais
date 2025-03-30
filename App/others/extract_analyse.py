from flask import Flask, request, jsonify
import boto3
import os

app = Flask(__name__)

# Configurações do AWS
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')

def upload_to_s3(file_path, bucket_name, object_name):
    try:
        s3_client.upload_file(file_path, bucket_name, object_name)
        return True
    except Exception as e:
        print(f"Erro ao enviar arquivo para o S3: {e}")
        return False

def analyze_expense(bucket_name, object_name):
    try:
        response = textract_client.analyze_expense(
            Document={'S3Object': {'Bucket': bucket_name, 'Name': object_name}}
        )
        
        text = ""
        detection_list = []
        summary_detection_list = []
        unnecessary_types = ['ITEM', 'QUANTITY', 'PRODUCT_CODE']

        for item in response['ExpenseDocuments']:
            # Extrair texto bruto
            for block in item.get('Blocks', []):
                if 'Text' in block:
                    text += block['Text'] + ' '

            # Processar itens da fatura
            for line_item_group in item.get('LineItemGroups', []):
                for line_items in line_item_group.get('LineItems', []):
                    for expense_field in line_items.get('LineItemExpenseFields', []):
                        if expense_field:
                            entry = {
                                'Type': expense_field.get('Type', {}).get('Text', ''),
                                'TypeConfidence': expense_field.get('Type', {}).get('Confidence', 0),
                                'Text': expense_field.get('ValueDetection', {}).get('Text', ''),
                                'ValueConfidence': expense_field.get('ValueDetection', {}).get('Confidence', 0)
                            }
                            if entry['Type'] not in unnecessary_types:
                                detection_list.append(entry)

            # Processar campos resumidos
            for summary_field in item.get('SummaryFields', []):
                entry = {
                    'Type': summary_field.get('Type', {}).get('Text', ''),
                    'TypeConfidence': summary_field.get('Type', {}).get('Confidence', 0),
                    'Text': summary_field.get('ValueDetection', {}).get('Text', ''),
                    'ValueConfidence': summary_field.get('ValueDetection', {}).get('Confidence', 0)
                }
                if entry['Type'] not in unnecessary_types:
                    summary_detection_list.append(entry)

        return {
            'extractedText': text.strip(),
            'extractedTextSummary': summary_detection_list,
            'extractedTextInfo': detection_list
        }
        
    except Exception as e:
        print(f"Erro ao analisar despesa: {e}")
        return None

@app.route('/api/v1/invoice', methods=['POST'])
def process_invoice():
    files = request.files.getlist('file')
    if not files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    bucket_name = "testandocriarbuckernomeusss"
    results = []

    for file in files:
        file_name = file.filename
        if not file_name:
            results.append({"error": "Nome inválido", "filePath": ""})
            continue

        file_path = f"temp_{file_name}"
        try:
            file.save(file_path)
        except Exception as e:
            print(f"Erro ao salvar temporário: {e}")
            results.append({"error": "Erro interno", "filePath": file_name})
            continue

        # Upload para S3
        if not upload_to_s3(file_path, bucket_name, file_name):
            results.append({"error": "Falha no upload", "filePath": file_name})
            os.remove(file_path)
            continue

        # Processar análise
        analysis = analyze_expense(bucket_name, file_name)
        os.remove(file_path)

        if not analysis:
            results.append({"error": "Falha na análise", "filePath": file_name})
        else:
            results.append({
                "filePath": file_name,
                "extractedText": analysis['extractedText'],
                "extractedTextSummary": analysis['extractedTextSummary'],
                "extractedTextInfo": analysis['extractedTextInfo']
            })

    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)