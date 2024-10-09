import json
import hmac
import hashlib
import requests
import os

def lambda_handler(event, context):
    print(event)
    
    try:
        # Token de verificación de WhatsApp (cambiar por el tuyo)
        verify_token = os.environ.get('VERIFY_TOKEN', 'VERYFY')
        app_secret = os.environ.get('APP_SECRET', '')

        # Validar el token recibido en el query string
        if 'queryStringParameters' in event and event['queryStringParameters']:
            queryParams = event['queryStringParameters']
            if 'hub.verify_token' in queryParams and queryParams['hub.verify_token'] == verify_token:
                challenge = queryParams['hub.challenge']
                return {
                    'statusCode': 200,
                    'body': challenge
                }
            else:
                return {
                    'statusCode': 403,
                    'body': 'Forbidden'
                }
        
        # Procesar el cuerpo del mensaje entrante
        token = os.environ.get('WHATSAPP_TOKEN')
        body = json.loads(event['body'])

        # Validar la firma de la solicitud (opcional)
        if app_secret:
            signature = event['headers'].get('x-hub-signature-256')
            expected_signature = 'sha256=' + hmac.new(app_secret.encode(), event['body'].encode(), hashlib.sha256).hexdigest()
            if signature != expected_signature:
                return {
                    'statusCode': 403,
                    'body': 'Forbidden'
                }
        
        if body.get('object'):
            entry = body.get('entry', [])
            if entry and entry[0].get('changes'):
                changes = entry[0].get('changes', [])
                if changes and changes[0].get('value'):
                    value = changes[0].get('value')
                    if value.get('messages') and value['messages'][0].get('text'):
                        phone_number_id = value['metadata']['phone_number_id']
                        from_number = value['messages'][0]['from']
                        
                        # Aquí debes especificar el nombre de la plantilla y el idioma
                        template_name = "your_template_name"  # Reemplaza con el nombre real de tu plantilla
                        language_code = "en_US"  # Reemplaza con el código de idioma de tu plantilla
                        
                        # Enviar la plantilla
                        response = requests.post(
                            f"https://graph.facebook.com/v20.0/{phone_number_id}/messages",
                            headers={"Content-Type": "application/json"},
                            json={
                                "messaging_product": "whatsapp",
                                "to": from_number,
                                "type": "template",
                                "template": {
                                    "name": template_name,
                                    "language": {
                                        "code": language_code
                                    },
                                    # Si tu plantilla tiene variables, puedes incluirlas aquí
                                    # "components": [
                                    #     {
                                    #         "type": "body",
                                    #         "parameters": [
                                    #             {"type": "text", "text": "variable_value_1"},
                                    #             {"type": "text", "text": "variable_value_2"}
                                    #         ]
                                    #     }
                                    # ]
                                }
                            },
                            params={"access_token": token},
                        )
                        
                        print("Response:", response.text)
                        print("Response:", response)
                        
                        if response.status_code == 200:
                            return {'statusCode': 200}
                        else:
                            return {'statusCode': response.status_code, 'body': response.text}

    except Exception as e:
        print("ERROR:", e)
        return {
            'statusCode': 500,
            'body': json.dumps('Error interno del servidor')
        }

    return {
        'statusCode': 400,
        'body': 'Bad Request'
    }
