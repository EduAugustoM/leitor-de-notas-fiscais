import boto3

#definição do client e credenciais
client = boto3.client('s3',
                  aws_access_key_id='AKIAJZJZQZQZQZQZQZQ',
                  aws_secret_access_key='DFGSDFSFGSDFGWERTWERGDFGDFGERGDFGDFGDFG',
                  aws_session_token='...',
                  region_name='us-east-1')

#criar bucket
response = client.create_bucket(
    Bucket='TESTECRIARBUCKET',
)

print("Bucket criado com sucesso:", response)