import json
import requests
import time
import boto3

# Inicializar DynamoDB
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('UserStates')
tableUser = dynamodb.Table('users')

def lambda_handler(event, context):
    try:
        if isinstance(event, str):
            event = json.loads(event)

        # Extraer la información relevante del evento
        token = event.get('token')
        phone_number_id = event.get('idPhone')
        user_code_info = event.get('user_code')
        from_number = user_code_info[0].get('from')
        timestamp = int(time.time())
        
        # Normalizar el número
        if from_number.startswith("521"):
            modified_number = "52" + from_number[3:]
        else:
            modified_number = from_number
        
        user_message = user_code_info[0].get('text', {}).get('body')
        
        if ':' in user_message:
            username, code = user_message.split(':', 1)
            print('CREDENCIALES', username, code)
            # Verificar si las credenciales son correctas
            user_name = validate_credentials(username, code)
            if user_name:
                message = f"Credenciales correctas. Hola {user_name} 😃 , por favor ingresa a nuestro catálogo y envia tu pedido. "
                send_text_message(phone_number_id, modified_number, message, token)
                # Cambiar el estado del usuario
                update_user_state(modified_number, "PROCESS_ORDER", timestamp,user_name)
                return {
                    'statusCode': 200,
                    'body': f"Message sent: Credenciales correctas. Bienvenido, {user_name}."
                }
            else:
                message = "Credenciales incorrectas. Por favor, inténtalo de nuevo."
                send_text_message(phone_number_id, modified_number, message, token)
                update_user_state(modified_number, "CREDENTIALS_RECEIVED", timestamp)
                return {
                    'statusCode': 200,
                    'body': 'Message sent: Credenciales incorrectas. Estado actualizado.'
                }
        else:
            send_text_message(phone_number_id, modified_number, 'Formato incorrecto. Por favor, inténtalo de nuevo.', token)
            update_user_state(modified_number, "CREDENTIALS_RECEIVED", timestamp)
            return {
                'statusCode': 200,
                'body': 'Message sent: Formato incorrecto. Estado actualizado.'
            }
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {
            'statusCode': 500,
            'body': f"Error interno del servidor: {str(e)}"
        }
    
def validate_credentials(username, code):
    try:
        # Consultar la tabla DynamoDB para verificar las credenciales
        response = tableUser.get_item(Key={'username': username})
        if 'Item' in response:
            stored_code = response['Item'].get('code')
            user_name = response['Item'].get('nombre')  # Supongamos que tienes una columna 'name' en DynamoDB
            if stored_code == code:
                return user_name  # Devuelve el nombre si las credenciales son correctas
            else:
                return None
        return None
    except Exception as e:
        print(f"Failed to validate credentials: {str(e)}")
        raise


def send_text_message(phone_number_id, to_number, text, token):
    try:
        response = requests.post(
            f"https://graph.facebook.com/v20.0/{phone_number_id}/messages",
            headers={"Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "text",
                "text": {
                    "body": text
                }
            },
            params={"access_token": token},
        )
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        print(f"Failed to send message: {str(e)}")
        raise

def update_user_state(user_id, state, timestamp, user_name=None):
    try:
        # Preparar la expresión de actualización
        update_expression = "SET #s = :state, #t = :timestamp"
        expression_attribute_names = {
            '#s': 'State',
            '#t': 'Timestamp'
        }
        expression_attribute_values = {
            ':state': state,
            ':timestamp': timestamp
        }
        
        # Si user_name se proporciona, agregarlo a la expresión de actualización
        if user_name is not None:
            update_expression += ", #u = :user_name"
            expression_attribute_names['#u'] = 'user_name'
            expression_attribute_values[':user_name'] = user_name
        
        # Realizar la actualización
        table.update_item(
            Key={'UserId': user_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values
        )
    except Exception as e:
        print(f"Failed to update user state: {str(e)}")
        raise



def get_user_state(user_id):
    try:
        response = table.get_item(Key={'UserId': user_id})
        return response.get('Item')
    except Exception as e:
        print(f"Failed to get user state: {str(e)}")
        raise

def clear_user_state(user_id):
    try:
        table.delete_item(
            Key={
                'UserId': user_id
            }
        )
    except Exception as e:
        print(f"Failed to clear user state: {str(e)}")
        raise
    
def send_template_message(phone_number_id, to_number, template_name, token):
    response = requests.post(
        f"https://graph.facebook.com/v20.0/{phone_number_id}/messages",
        headers={"Content-Type": "application/json"},
        json={
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": "es"
                }
            }
        },
        params={"access_token": token},
    )
    return response
