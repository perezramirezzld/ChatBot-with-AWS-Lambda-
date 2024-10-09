import json
import requests
import time
import boto3
import mercadopago
from boto3.dynamodb.conditions import Attr
from requests.auth import HTTPBasicAuth

# Inicializar DynamoDB
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('UserStates')
tableUser = dynamodb.Table('users')

# Información de pago
PAYPAL_LINK = "https://www.paypal.me/tu_link_paypal/150.00"  # Enlace directo a tu PayPal
PAYPAL_CLIENT_ID = 'ASNaCd1gt7A8b-qGOHlCJWSF0NMvGENNc--iBknRbdKlHAuB9jEqIf4J2gDF3nH7_VrOdDM-04P5QOvq'
PAYPAL_CLIENT_SECRET = 'EA5KeBrkdogJp0aEruEW9rbN_yB35KCzTbUM0yNSLruuijuxuuusjgM2iFqyol2_UP2PdXG3WtrULbWQ'
ACCESS_TOKENMP = "APP_USR-6915558597906759-100314-9525ff3db78d4642435fea5b12eed333__LC_LD__-269840774"  

def lambda_handler(event, context):
    try:
        if isinstance(event, str):
            event = json.loads(event)
        print(event)

        # Extraer la información relevante del evento
        token = event.get('token')
        pedido = json.loads(event.get('pedido'))  # Convertir pedido a diccionario
        phone_number_id = event.get('idPhone')
        user_code_info = event.get('user_code')
        from_number = user_code_info[0].get('from')
        timestamp = int(time.time())

        # Normalizar el número
        if from_number.startswith("521"):
            modified_number = "52" + from_number[3:]
        else:
            modified_number = from_number

        # Obtener el estado del usuario desde DynamoDB
        user_state = get_user_state(modified_number)
        user_name = user_state['user_name'] if user_state else "Cliente"
        print(f'NOMBRE DEL USUARIO: {user_name}, Pedido: {pedido}')
        
        # Validar el estado del pedido
        if event.get('state') == "ORDER_CONFIRMED":
            print("Estado del pedido es ORDER_CONFIRMED")
            
            try:
                total_amount = float(pedido['TotalAmount'])  # Convertir a float
            except ValueError:
                return {'statusCode': 400, 'body': 'El monto total no es válido'}
             # Enviar mensaje con botones interactivos para elegir forma de pago
            responsed = send_payment_confirmationX(phone_number_id, modified_number, token, total_amount)
            response = send_payment_confirmation(phone_number_id, modified_number, token, total_amount)
            response2 = send_payment_confirmation2(phone_number_id, modified_number, token, total_amount)
             # Actualizar estado del usuario
            # Verificar si la respuesta fue exitosa (código 200)
            if response.status_code == 200 and response2.status_code == 200:
                update_user_state(modified_number, "AWAITING_FOR_PAYMENT", timestamp)
                return {
                    'statusCode': 200,
                    'body': 'Mensaje de opciones de pago enviado. Estado actualizado.'
                }
            else:
                # Imprimir el código de error devuelto por la API
                print(f"Error al enviar mensaje de pago: {response.status_code} - {response.text}")
                return {
                    'statusCode': response.status_code,
                    'body': f"Error al enviar mensaje de pago: {response.status_code} - {response.text}"
                }
        else:
            return {
                'statusCode': 200,
                'body': 'El estado del pedido no es CONFIRMATION_ORDER. No se envió el mensaje.'
            }
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {
            'statusCode': 500,
            'body': f"Error interno del servidor: {str(e)}"
        }
    
# def send_payment_options(phone_number_id, to_number, token, monto):
#     """
#     Enviar opciones de pago usando una plantilla previamente configurada en la API de WhatsApp.
#     """
#     # Generar el enlace de Mercado Pago dinámicamente
#     #mercado_pago_link = crear_pago_mercado_pago(email,monto)

#     url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
#     headers = {
#         "Content-Type": "application/json",
#         "Authorization": f"Bearer {token}"
#     }

#     # Cuerpo del mensaje usando la plantilla con variables dinámicas para las URLs
#     data = {
#         "messaging_product": "whatsapp",
#         "to": to_number,
#         "type": "template",
#         "template": {
#             "name": "metodo_pago",  # Nombre de la plantilla
#             "language": {
#                 "code": "es"  # Idioma de la plantilla
#             },
#             "components": [
#                 {
#                     "type": "button",
#                     "sub_type": "url",
#                     "index": "0",  # Botón de Mercado Pago
#                     "parameters": [
#                         {
#                             "type": "text",
#                             "text": PAYPAL_LINK  # Enlace dinámico de Mercado Pago
#                         }
#                     ]
#                 },
#                 {
#                     "type": "button",
#                     "sub_type": "url",
#                     "index": "1",  # Botón de PayPal
#                     "parameters": [
#                         {
#                             "type": "text",
#                             "text": PAYPAL_LINK  # Enlace dinámico de PayPal
#                         }
#                     ]
#                 }
#             ]
#         }
#     }

#     response = requests.post(url, headers=headers, json=data)
#     print(f"Respuesta template de la API de WhatsApp: {response.status_code}, {response.text}")
#     return response


def send_payment_confirmationX(phone_number_id, to_number, token, monto):
    """
    Enviar opciones de pago con botones interactivos para Mercado Pago y PayPal usando botones de tipo "call_to_action".
    """
    email = obtener_email_por_numero_telefono(to_number)
    mercado_pago_link = crear_pago_mercado_pago(email, phone_number_id, to_number, token, monto)
    paypal_link = crear_pago_paypal(phone_number_id, to_number, token, monto)

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    # Cuerpo del mensaje interactivo con botones de tipo "call_to_action"
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "header": {
                "type": "text",
                "text": "Selecciona tu método de pago"
            },
            "body": {
                "text": "Elige cómo deseas pagar:"
            },
            "action": {
                "buttons": [
                    {
                        "type": "call_to_action",  # Botón interactivo de llamada a la acción
                        "text": "Pagar con Mercado Pago",
                        "url": mercado_pago_link
                    },
                    {
                        "type": "call_to_action",  # Botón interactivo de llamada a la acción
                        "text": "Pagar con PayPal",
                        "url": paypal_link
                    }
                ]
            }
        }
    }

    response = requests.post(url, headers=headers, json=data)
    print(f"Respuesta de la API de WhatsApp: {response.status_code}, {response.text}")
    return response

def send_payment_confirmation2(phone_number_id, to_number, token, monto):
    """
    Enviar opciones de pago con botones interactivos de tipo URL para Mercado Pago y PayPal sin usar plantilla.
    """
    paypal_link = crear_pago_paypal(phone_number_id, to_number, token, monto)
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    # Cuerpo del mensaje interactivo con botones de URL (cta_url)
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
             "body": {
                "text": "."
            },
            "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": "Pay pal",
                "url": paypal_link
                }
            }
        }
    }

    response = requests.post(url, headers=headers, json=data)
    print(f"Respuesta 2 de la API de WhatsApp: {response.status_code}, {response.text}")
    return response

def send_payment_confirmation(phone_number_id, to_number, token, monto):
    """
    Enviar opciones de pago con botones interactivos de tipo URL para Mercado Pago y PayPal sin usar plantilla.
    """
    email = obtener_email_por_numero_telefono(to_number)

    mercado_pago_link = crear_pago_mercado_pago(email,phone_number_id, to_number, token, monto)
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    # Cuerpo del mensaje interactivo con botones de URL (cta_url)
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "cta_url",  # Definimos un botón interactivo
            "body": {
                "text": f"Selecciona tu método de Pago 😃💵"
            },
            "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": "Mercado Pago",
                "url": mercado_pago_link
                }
            }
        }
    }

    response = requests.post(url, headers=headers, json=data)
    print(f"Respuesta 1 de la API de WhatsApp: {response.status_code}, {response.text}")
    return response

def obtener_token_paypal():
    """
    Función para obtener el token de acceso desde la API de PayPal.
    """
    url = "https://api-m.paypal.com/v1/oauth2/token"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en_US"
    }
    data = {
        "grant_type": "client_credentials"
    }

    response = requests.post(url, headers=headers, data=data, auth=HTTPBasicAuth(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET))
    print(f"Respuesta de PayPal obtener Token: {response}")
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"Error al obtener el token de PayPal: {response.status_code}, {response.text}")

def crear_pago_paypal(phone_number_id, to_number, token, monto):
    """
    Crear un link de pago en PayPal y devolver la URL de aprobación.
    """
    token = obtener_token_paypal()
    url = "https://api-m.paypal.com/v2/checkout/orders"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    # Datos de la orden de pago
    order_data = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": "MXN",
                    "value": str(monto)
                }
            }
        ],
        "application_context": {
            "return_url": f"https://mylapmn6oyg7ywbeiqcsuy3qoq0zjins.lambda-url.us-east-1.on.aws/success?phone_number_id={phone_number_id}&to_number={to_number}&token={token}",
            "cancel_url": f"https://mylapmn6oyg7ywbeiqcsuy3qoq0zjins.lambda-url.us-east-1.on.aws/failure?phone_number_id={phone_number_id}&to_number={to_number}&token={token}"
        }
    }

    # Crear la orden de pago
    response = requests.post(url, headers=headers, json=order_data)
    print(f"Respuesta de PayPal crear pago: {response}")
    if response.status_code == 201:
        order = response.json()
        # Buscar el link de aprobación
        for link in order["links"]:
            if link["rel"] == "approve":
                return link["href"]
    else:
        raise Exception(f"Error al crear el pago en PayPal: {response.status_code}, {response.text}")

def crear_pago_mercado_pago(email,phone_number_id, to_number, token, monto):
    """
    Crea un link de pago en Mercado Pago y devuelve la URL del pago.
    """
    # Inicializar el SDK de Mercado Pago con tu Access Token
    sdk = mercadopago.SDK(ACCESS_TOKENMP)
    
    # Datos de la preferencia de pago con 'wallet_purchase'
    preference_data = {
        "items": [
            {
                "title": 'Ecoshell Online',  # Nombre del producto o servicio
                "unit_price": monto, 
                "currency_id": "MXN", # Monto proporcionado dinámicamente
                "quantity": 1,  # Cantidad
                "description": "Ecoshell Online, Whattsap"  # Descripción del producto o servicio
            }
        ],
        "purpose": "wallet_purchase",  # Propósito de la compra (wallet_purchase)
        "payer": {
            "email": email  # Puedes cambiarlo según el pagador
        },
        "back_urls": {
            "success": f"https://mylapmn6oyg7ywbeiqcsuy3qoq0zjins.lambda-url.us-east-1.on.aws/success?phone_number_id={phone_number_id}&to_number={to_number}&token={token}",
            "failure": f"https://mylapmn6oyg7ywbeiqcsuy3qoq0zjins.lambda-url.us-east-1.on.aws/failure?phone_number_id={phone_number_id}&to_number={to_number}&token={token}",
            "pending": f"https://mylapmn6oyg7ywbeiqcsuy3qoq0zjins.lambda-url.us-east-1.on.aws/pending?phone_number_id={phone_number_id}&to_number={to_number}&token={token}"
        },
        "auto_return": "approved"
    }

    # Crear la preferencia de pago en Mercado Pago
    preference_response = sdk.preference().create(preference_data)
    
    # Imprimir la respuesta completa para depuración
    print("Respuesta completa de Mercado Pago:", preference_response)

    # Verificar que la respuesta contiene 'response' y 'init_point'
    if "response" in preference_response and "init_point" in preference_response["response"]:
        # Retorna el link de pago para el entorno de producción
        return preference_response["response"]["init_point"]
    else:
        raise Exception(f"Error en la creación de la preferencia: {preference_response['response']}")

def obtener_email_por_numero_telefono(phone_number):
    """
    Obtener el email desde la tabla users usando el número de teléfono como clave.
    """
    try:
        # Obtener el registro de la tabla UserStates usando el número de teléfono
        response = table.get_item(Key={'UserId': phone_number})

        # Extraer el campo 'name' de la tabla UserStates
        if 'Item' in response:
            name = response['Item'].get('user_name')  # Cambiado a 'user_name'
            if not name:
                print("No se encontró el nombre en la tabla UserStates")
                return None
        else:
            print(f"No se encontró el número de teléfono {phone_number} en la tabla UserStates")
            return None

        # Usar un scan para buscar el email en la tabla users filtrando por 'nombre'
        response_user = tableUser.scan(
            FilterExpression=Attr('nombre').eq(name)
        )

        # Verificar si se encontró algún elemento
        if 'Items' in response_user and len(response_user['Items']) > 0:
            email = response_user['Items'][0].get('email')  # Obtener el primer resultado
            if email:
                print(f"Email encontrado: {email}")
                return email
            else:
                print(f"No se encontró el email para el nombre {name}")
                return None
        else:
            print(f"No se encontró el nombre {name} en la tabla users")
            return None
    except Exception as e:
        print(f"Error al obtener el email: {str(e)}")
        return None

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
