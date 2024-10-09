import json
import requests
import time
import boto3
import re

# Inicializar DynamoDB
dynamodb = boto3.resource('dynamodb')
tableOrder = dynamodb.Table('orders')
table = dynamodb.Table('UserStates')

def lambda_handler(event, context):
    try:
        if isinstance(event, str):
            event = json.loads(event)
        print(event)

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

        if event.get('state') == 'PROCESS_ORDER':
            # Extraer la información del pedido
            order_info = user_code_info[0].get('order', {})
            product_items = order_info.get('product_items', [])

            # Generar el mensaje de confirmación del pedido
            confirmation_message = "Te confirmo tu pedido:\n\n"
            total_amount = 0
            for item in product_items:
                product_id = item.get('product_retailer_id')
                quantity = item.get('quantity')
                price = item.get('item_price')
                currency = item.get('currency', 'MXN')

                # Calcular el precio total del ítem
                total_item_price = quantity * price
                total_amount += total_item_price

                # Añadir al mensaje de confirmación
                confirmation_message += f"- Código de Producto: {product_id}, Cantidad: {quantity}, Total: {total_item_price:.2f} {currency} 🛒\n"

            # Convertir total_amount a string antes de almacenarlo
            total_amount_str = str(round(total_amount, 2))

            # Convertir product_items a JSON string para almacenarlo en DynamoDB
            product_items_str = json.dumps(product_items)

            confirmation_message += f"\nTotal a pagar: ${total_amount_str} {currency}"
            print("CONFIRMATION MESSAGE", confirmation_message)

            shipping_message = (
                "Hemos recibido tu pedido. Ahora necesitamos los detalles de envío:\n"
                "Por favor, Escribe ...\n"
                "1. (Dirección de envío) 🏠 (obligatoria)\n"
                "2. (Detalles de envío) 🚚 (opcional)\n"
                "3. (CIF) (si requiere factura) 🧾 (opcional)"
            )

            # Enviar el mensaje de confirmación y actualizar el estado del usuario y del pedido
            update_user_state(modified_number, "AWAITING_SHIPPING_DETAILS", timestamp)
            update_order_state(modified_number, 'AWAITING_SHIPPING_DETAILS', product_items_str, total_amount_str)

            response = send_text_message(phone_number_id, modified_number, shipping_message, token)
            if response.status_code == 200:
                return {'statusCode': 200, 'body': 'Pedido recibido y solicitud de detalles de envío enviada exitosamente'}
            else:
                print("Failed to send order confirmation message template:", response.text)
                return {'statusCode': response.status_code, 'body': response.text}

        else:
            body = user_code_info[0].get('text', {}).get('body')

            # Validar que el usuario proporcionó "1. (dirección)" y "2. (detalles)"
            if '1.' not in body:
                incomplete_message = (
                    "Por favor, completa el proceso anterior enviando los datos obligatorios:\n"
                    "Recuerda poner 1. - Calle, Numero, Código Postal, Ciudad.  🏠 \n"
                    "Ejemplo:\n"
                    "1. Calle 123, Colonia, Ciudad, Estado, Código Postal\n"
                    "2. Dejar en la puerta principal"
                )
                response = send_text_message(phone_number_id, modified_number, incomplete_message, token)
                return {'statusCode': 200, 'body': 'Incomplete shipping details request sent'}

            # Extraer y limpiar el texto de la dirección de envío
            body = clean_text(body)
            shipping_details = extract_shipping_details(body)
            print("SHIPPING DETAILS", shipping_details)

            # Verificar si la dirección de envío está completa
            if not shipping_details['address']:
                incomplete_message = (
                    "Por favor, asegúrate de proporcionar al menos:\n"
                    "1. Dirección de envío 🏠 (obligatoria)\n"
                )
                response = send_text_message(phone_number_id, modified_number, incomplete_message, token)
                return {'statusCode': 200, 'body': 'Incomplete shipping details request sent'}

            # Obtener el pedido almacenado previamente por el usuario
            previous_order = get_order_by_user(modified_number)
            if not previous_order:
                return {'statusCode': 400, 'body': 'No se encontró un pedido anterior'}
              # Convertir ArrayProducts de cadena JSON a lista
            try:
                array_products = json.loads(previous_order.get('ArrayProducts', '[]'))
            except json.JSONDecodeError:
                return {'statusCode': 500, 'body': 'Error al decodificar los productos del pedido anterior'}

            # Verificar que array_products sea una lista
            if not isinstance(array_products, list):
                return {'statusCode': 400, 'body': 'El formato de los productos es incorrecto'}
            print("PREVIOUS ORDER", previous_order)
            # Confirmar el pedido y los detalles de envío
            final_confirmation_message = (
            "Gracias por proporcionarnos los detalles de envío.\n"
            "Te confirmo tu pedido:\n\n"
            )
            print("PREVIUS AARAY", array_products)
            # Verificar que el TotalAmount exista y sea del tipo correcto
            total_amount = previous_order.get('TotalAmount')
            if not isinstance(total_amount, (int, float, str)) or not total_amount:
                return {'statusCode': 400, 'body': 'El monto total del pedido es inválido'}

            # Iterar sobre los productos y generar el mensaje de confirmación
            for item in array_products:
            # Verificar que item sea un diccionario y contenga las claves necesarias
                if not isinstance(item, dict):
                 continue

                product_id = item.get('product_retailer_id', 'N/A')
                quantity = item.get('quantity', 0)
                item_price = item.get('item_price', 0.0)
                total_item_price = quantity * item_price
                currency = item.get('currency', 'MXN')

                final_confirmation_message += f"- Código de Producto: {product_id}, Cantidad: {quantity}, Total: {total_item_price:.2f} {currency} 🛒\n"

            final_confirmation_message += f"\nTotal a pagar: ${total_amount} {currency}\n\n"
            final_confirmation_message += f"Dirección de envío: {shipping_details['address']}\n"

            # Incluir detalles y CIF si están presentes
            if shipping_details['details'] != 'Nada':
                final_confirmation_message += f"Detalles de envío: {shipping_details['details']}\n"
            if shipping_details['cif'] != 'No CIF proporcionado':
                final_confirmation_message += f"CIF: {shipping_details['cif']}\n"
            print("FINAL CONFIRMATION MESSAGE", final_confirmation_message)
            response = send_order_confirmation(phone_number_id, modified_number, final_confirmation_message, token)
            if response.status_code == 200:
                update_user_state(modified_number, "PROCESS_CONFIRMED", timestamp)
                return {'statusCode': 200, 'body': 'Pedido confirmado con detalles de envío'}
            else:
                print("Failed to send final confirmation message:", response.text)
                return {'statusCode': response.status_code, 'body': response.text}

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {
            'statusCode': 500,
            'body': f"Error interno del servidor: {str(e)}"
        }
        
        
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

def send_order_confirmation(phone_number_id, to_number,final_confirmation_message, token):
    """
    Enviar mensaje interactivo de confirmación de pedido con botones en WhatsApp.
    """
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    # Cuerpo del mensaje interactivo con botones
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "button",  # Tipo de mensaje interactivo
            "header": {
                "type": "text",  # Tipo de encabezado
                "text": "Confirmación de Pedido"  # Texto del encabezado
            },
            "body": {
                "text": f"{final_confirmation_message}"  # Texto del cuerpo con detalles dinámicos del pedido
            },
            "footer": {
                "text": "Presiona Confirmar para proceder con el pedido."  # Texto opcional del pie
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",  # Botón de respuesta rápida
                        "reply": {
                            "id": "confirm_order",  # ID del botón de confirmación
                            "title": "Confirmar"  # Texto del botón de confirmación
                        }
                    },
                    {
                        "type": "reply",  # Botón de respuesta rápida
                        "reply": {
                            "id": "cancel_order",  # ID del botón de cancelación
                            "title": "Cancelar"  # Texto del botón de cancelación
                        }
                    },
                ]
            }
        }
    }

    response = requests.post(url, headers=headers, json=data)
    print(f"Respuesta de la API de WhatsApp: {response.status_code}, {response.text}")
    return response
    
def update_order_state(user_id, state,product_items,total_amount):
    tableOrder.put_item(
        Item={
            'UserId': user_id,
            'State': state,
            'ArrayProducts': product_items,
            'TotalAmount': total_amount
        }
    )

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

# Función para extraer detalles de envío desde el texto enviado por el usuario
def extract_shipping_details(body):
    # Buscar los detalles de envío en el formato numerado
    address_index = body.find("1.")
    details_index = body.find("2.")
    cif_index = body.find("3.")
    
    address = body[address_index + 2:].split("2.")[0].strip() if address_index != -1 else None
    details = body[details_index + 2:].split("3.")[0].strip() if details_index != -1 else 'Nada'
    cif = body[cif_index + 2:].strip() if cif_index != -1 else 'No CIF proporcionado'
    
    return {
        'address': address,
        'details': details,
        'cif': cif
    }

# Función para obtener un pedido por usuario
def get_order_by_user(user_id):
    try:
        response = tableOrder.get_item(Key={'UserId': user_id})
        return response.get('Item')
    except Exception as e:
        print(f"Error al obtener el pedido: {str(e)}")
        return None

def clean_text(text):
    # Elimina cualquier carácter no visible como \u2060 o similares
    cleaned_text = re.sub(r'[\u2060]', '', text)  # Puedes ajustar este regex para eliminar otros caracteres invisibles
    return cleaned_text.strip()