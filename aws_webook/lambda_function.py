import json
import requests
import os
import time
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('UserStates') 
tableOrder = dynamodb.Table('orders')
stepfunctions_client = boto3.client('stepfunctions')

TIMEOUT_THRESHOLD = 120

def lambda_handler(event, context):
    try:
        verify_token = 'VERYFY'
        token = 'EAANGzyTZB7dIBOwWYNEwQ1DOvR4sxLqRN8SlNynrffMJygdY9ekzCq5EzBWFveHtdijTP777azZCIciOyZA3ncJ7N35j9deFnZBp3yNrKCVRGyjzFC7lC0Hn9zaDzpPd41PgFrIZBhVe79cpZCHoVOoFGr2PeRoW368FBhZCayIYjHE7SseWJ1vqgFLIS7Qr6BD4k78eA4AnfZBuxYldZCQUaYCSmUeUZD'
        step_function_arn = 'arn:aws:states:us-east-1:533267113681:stateMachine:MyStateMachine-9i2y62kep'
        
        body = json.loads(event['body'])
        print("INFORMACION ",body)
        if body.get('object') == 'whatsapp_business_account':
            entry = body.get('entry', [])
            if entry and entry[0].get('changes'):
                changes = entry[0].get('changes', [])
                if changes and changes[0].get('value'):
                    value = changes[0].get('value')
                    if value.get('messages'):
                        phone_number_id = value['metadata']['phone_number_id']
                        from_number = value['messages'][0]['from']
                        msg_body = value['messages'][0].get('text', {}).get('body')
                        informacion = value['messages']
                        timestamp = int(time.time())
                        
                        if from_number.startswith("521"):
                            modified_number = "52" + from_number[3:]
                        else:
                            modified_number = from_number
                        
                        # Obtener el estado del usuario desde DynamoDB
                        user_state = get_user_state(modified_number)
                        
                        # Validar si han pasado más de 2 minutos desde la última interacción
                        if user_state:
                            last_interaction_time = user_state['Timestamp']
                            time_diff = timestamp - last_interaction_time
                            
                            if time_diff > TIMEOUT_THRESHOLD:
                                # Reiniciar el estado del usuario y enviar mensaje de sesión reiniciada
                                clear_user_state(modified_number)
                                return lambda_handler(event, context)
                            
                        # Si es el primer mensaje, enviar mensaje de bienvenida y guardar el estado
                        if not user_state:
                            if not msg_body:
                                send_text_message(phone_number_id, modified_number, "Por favor, completa el proceso anterior.", token)
                                return {'statusCode': 200, 'body': 'Reminder sent'}
                            
                            response = send_template_message(phone_number_id, modified_number, token)
                            if response.status_code == 200:
                                update_user_state(modified_number, "WELCOME_SENT", timestamp)
                                return {'statusCode': 200, 'body': 'Welcome template sent successfully'}
                            else:
                                return {'statusCode': response.status_code, 'body': response.text}
                        
                        else:
                            # Continuar en función del estado del usuario
                            if user_state['State'] in ["WELCOME_SENT", "CREDENTIALS_RECEIVED"]:
                                if not msg_body:
                                    send_text_message(phone_number_id, modified_number, "Por favor, completa el proceso anterior.", token)
                                    return {'statusCode': 200, 'body': 'Reminder sent'}
                                
                                update_user_state(modified_number, "CREDENTIALS_RECEIVED", timestamp)
                                model = {
                                    "token": token,
                                    "idPhone": phone_number_id,
                                    "user_code": informacion,
                                    "state": "CREDENTIALS_RECEIVED"
                                }
                                send_text_message(phone_number_id, modified_number, "Credenciales recibidas, estamos validando...", token)
                                response = stepfunctions_client.start_execution(
                                    stateMachineArn=step_function_arn,
                                    input=json.dumps({"user_code": model})
                                )
                                return {'statusCode': 200, 'body': 'Step Function initiated successfully'}
                            
                            elif user_state['State'] == "PROCESS_ORDER" or user_state['State'] == "AWAITING_SHIPPING_DETAILS" or user_state['State'] == "PROCESS_CONFIRMED":
                                estado = user_state['State']
                                message_type = informacion[0].get('type')
                                print("TIPO", message_type)
                                if message_type == 'order' or user_state['State'] == "AWAITING_SHIPPING_DETAILS":
                                    # Procesar el pedido
                                    model = {
                                        "token": token,
                                        "idPhone": phone_number_id,
                                        "user_code": informacion,
                                        "state": estado
                                    }
                                    response = stepfunctions_client.start_execution(
                                        stateMachineArn=step_function_arn,
                                        input=json.dumps({"user_code": model})
                                    )
                                    return {'statusCode': 200, 'body': 'Step Function initiated successfully'}
                                
                                elif message_type == 'interactive':
                                    UserOrder = get_order_state(modified_number)
                                    # Verificar si el mensaje es "Confirmar", "Cancelar", o si no se entiende
                                    interactive_data = informacion[0]['interactive']
                                    print("Informacion de mensaje",interactive_data)
                                    if interactive_data['type'] == 'button_reply':
                                        button_reply = interactive_data['button_reply']
                                        button_title = button_reply['title'].strip().lower()
                                        button_id = button_reply['id']
                                        print("TITULO",button_title)
                                        if button_id == 'confirm_order' or button_title == 'Confirmar':
                                            send_text_message(phone_number_id, modified_number, "Pedido confirmado ✅... generando links de pago.", token)

                                            pedido_json = json.dumps(UserOrder, default=decimal_to_float)

                                            model = {
                                            "token": token,
                                            "pedido": pedido_json,
                                            "idPhone": phone_number_id,
                                            "user_code": informacion,
                                            "state": "ORDER_CONFIRMED"
                                            }
                                            response = stepfunctions_client.start_execution(
                                            stateMachineArn=step_function_arn,
                                            input=json.dumps({"user_code": model})
                                            )
                                            return {'statusCode': 200, 'body': 'Step Function 2do successfully, pedido confirmado.'}
                                    
                                        elif button_id == 'cancel_order' or button_title == 'Cancelar':
                                            update_user_state(modified_number, "PROCESS_ORDER", timestamp)
                                            send_text_message(phone_number_id, modified_number, "Pedido cancelado ❌, realiza nuevamente tu pedido., desde el catalogo .", token)
                                            return {'statusCode': 200, 'body': 'Pedido cancelado'}
                                        else:
                                            send_text_message(phone_number_id, modified_number, "No se entendió tu mensaje. Por favor,completa el proceso anterior.", token)
                                            return {'statusCode': 200, 'body': 'Mensaje no entendido'}
                                
                                else:
                                    send_text_message(phone_number_id, modified_number, "Por favor, completa el proceso anterior.", token)
                                    return {'statusCode': 200, 'body': 'Reminder sent'}

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
    
def decimal_to_float(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError("Object of type Decimal is not JSON serializable")
    

def send_template_message(phone_number_id, to_number, token):
    full_message = (
        f"*¡Hola! Bienvenido, Socio CANIRAC.*\n\n"
        "Por favor, proporciónanos tu usuario y código de acceso en formato 'Usuario:Código'.Sin espacios."
    )
    
    response = requests.post(
        f"https://graph.facebook.com/v20.0/{phone_number_id}/messages",
        headers={"Content-Type": "application/json"},
        json={
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {
                "body": full_message  # El mensaje completo con título y cuerpo
            }
        },
        params={"access_token": token},
    )
    print('RESPUESTA MENSAJE FORMATEADO', response.status_code, response.text)
    return response


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


def get_order_state(user_id):
    try:
        response = tableOrder.get_item(Key={'UserId': user_id})
        return response.get('Item')
    except Exception as e:
        print(f"EEROR Table: {str(e)}")
        raise

def get_user_state(user_id):
    response = table.get_item(Key={'UserId': user_id})
    return response.get('Item')

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
