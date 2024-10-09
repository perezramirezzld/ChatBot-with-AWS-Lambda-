import json
import boto3
import requests
import os
from botocore.exceptions import NoCredentialsError, ClientError

# Inicializar el cliente de DynamoDB
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('TokenWhats')

def lambda_handler(event, context):
    try:
        # Obtener las credenciales de tu aplicación de Meta desde las variables de entorno
        app_id = "922280422993362"
        app_secret = "0a59df84f4c3da53f2d3eead9474e631"
        short_lived_token = "EAANGzyTZB7dIBOxJF2fqaDfieffNwVoCkIBivZCghXRGpzhad0qlzb7q5ZBVOmuBAWqfkyFUkbgJojhwnZBxVsIzJZCUsyFzPzJPBekoR50HCNlGfaYpZAJKD4zmjHi2vvYUxyyJJ22ZA4BYTiNKt3GsCbTbSjHbJ6Hm7OiJWGB3ko8vyOaOapBiVvHGx6JtIU2ZBZAIiU4ZAIpoyPrnlc28UuGPAeRltc"

        # Construir la URL para obtener el token de largo plazo
        url = f"https://graph.facebook.com/v10.0/oauth/access_token?grant_type=fb_exchange_token&client_id={app_id}&client_secret={app_secret}&fb_exchange_token={short_lived_token}"
        
        # Realizar la solicitud a la API de Meta para generar el nuevo token
        response = requests.get(url)
        
        # Verificar si la respuesta es exitosa
        if response.status_code == 200:
            long_lived_token = response.json().get('access_token')
            
            # Almacenar el nuevo token en la tabla DynamoDB
            table.put_item(
                Item={
                    'token': 'whatsapp_access_token',
                    'access_token': long_lived_token
                }
            )
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Token de acceso de WhatsApp actualizado y almacenado correctamente.",
                    "access_token": long_lived_token
                })
            }
        else:
            return {
                "statusCode": response.status_code,
                "body": json.dumps({
                    "message": "Error al generar el token de acceso.",
                    "error": response.json()
                })
            }
    
    except (NoCredentialsError, ClientError) as e:
        print(f"Error al acceder a DynamoDB: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Error al acceder a DynamoDB.",
                "error": str(e)
            })
        }
    except requests.exceptions.RequestException as e:
        print(f"Error en la llamada a la API de Meta: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Error al conectar con la API de Meta.",
                "error": str(e)
            })
        }
    except Exception as e:
        print(f"Error inesperado: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Error interno del servidor.",
                "error": str(e)
            })
        }
