import json
import requests
import time
import boto3

# Crear el recurso DynamoDB
dynamodb = boto3.resource('dynamodb')
tableOrder = dynamodb.Table('orders')
table = dynamodb.Table('UserStates')

# Función principal de la Lambda
def lambda_handler(event, context):
    # Obtener la ruta (path) para saber si es success, failure o pending
    path = event['rawPath']
    print(event)
    # Obtener los parámetros de consulta de la URL
    query_parameters = event.get('queryStringParameters', {})

    # Extraer los parámetros que estás enviando
    phone_number_id = query_parameters.get('phone_number_id', None)
    to_number = query_parameters.get('to_number', None)
    token = query_parameters.get('token', None)
    timestamp = int(time.time())
    
    print(f"phone_number_id: {phone_number_id}, to_number: {to_number}, token: {token}")

    if not phone_number_id or not to_number or not token :
        return {
            "statusCode": 400,
            "body": json.dumps({
                "message": "Faltan parámetros necesarios en la URL."
            })
        }

    # Procesar según la ruta del evento
    if path == "/success":
        print("SUCCESS")
        # Enviar mensaje de confirmación de pago
        success_message = "¡Pago exitoso! Gracias por tu compra. Estamos procesando tu pedido."
        # Obtener la orden del usuario desde DynamoDB
        order = get_order_by_user(to_number)
        if not order:
            return {'statusCode': 400, 'body': json.dumps({'message': 'No se encontró un pedido anterior'})}
        
        try:
            array_products = json.loads(order.get('ArrayProducts', '[]'))
        except json.JSONDecodeError:
            return {'statusCode': 500, 'body': 'Error al decodificar los productos del pedido anterior'}

        # Verificar que array_products sea una lista
        if not isinstance(array_products, list):
            return {'statusCode': 400, 'body': 'El formato de los productos es incorrecto'}
        print("PREVIOUS ORDER", array_products)
        response = send_text_message(phone_number_id, to_number, success_message, token)
        clear_user_state(to_number)
        print(response)
        # Subir la orden a SAP
        sap_response = upload_order_to_sap(order)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Pago exitoso y pedido enviado a SAP.",
                "sap_response": sap_response
            })
        }

    elif path == "/failure":
        # Enviar mensaje de error de pago
        error_message = "Hubo un error en tu pago. Por favor, comunícate al número de soporte."
        send_text_message(phone_number_id, to_number, error_message, token)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Mensaje de error enviado al usuario."
            })
        }

    elif path == "/pending":
        # Enviar mensaje de pago pendiente
        pending_message = "Tu pago está pendiente. Te notificaremos cuando sea aprobado."
        send_text_message(phone_number_id, to_number, pending_message, token)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Mensaje de estado pendiente enviado al usuario."
            })
        }
    
    else:
        # Si la ruta no coincide con ninguna de las esperadas
        return {
            "statusCode": 400,
            "body": json.dumps({
                "message": "Ruta no válida."
            })
        }


# Función para enviar un mensaje de texto por WhatsApp
def send_text_message(phone_number_id, to_number, text, token):
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
    return response

# Función para obtener un pedido por usuario
def get_order_by_user(user_id):
    try:
        response = tableOrder.get_item(Key={'UserId': user_id})
        return response.get('Item')
    except Exception as e:
        print(f"Error al obtener el pedido: {str(e)}")
        return None

# Función para subir el pedido a SAP
def upload_order_to_sap(order):
    # Aquí deberías implementar la lógica para subir el pedido a SAP
    # usando las credenciales proporcionadas
    credentials = {
        "CompanyDB": "SBO_ECOSHELL",
        "UserName": "CHATBOT",
        "Password": "1234"
    }
    # Simular la carga a SAP
    print(f"Subiendo el pedido a SAP con las credenciales: {credentials} y el pedido: {order}")
    # Aquí puedes hacer una solicitud HTTP a la API de SAP si es necesario
    # return requests.post('URL_DE_SAP', json={...})
    return {"status": "success", "message": "Pedido subido a SAP"}

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