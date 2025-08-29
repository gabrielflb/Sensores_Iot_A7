import paho.mqtt.client as mqtt
import requests
import json
import time
import jwt
from collections import deque
import statistics
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FogNode:
    def __init__(self):
        # Configurações MQTT para comunicação com Edge
        self.mqtt_broker = "localhost"
        self.mqtt_port = 1883
        self.mqtt_topic_sensors = "sensors/data"
        self.mqtt_topic_actuator = "actuator/control"
        
        # Configurações HTTP para comunicação com Cloud
        self.cloud_api_url = "http://localhost:5000/api/data"  #
        self.login_url = "http://localhost:5000/api/login"     
        self.auth_token = None
        self.token_expiration = None
        
        # Buffer de dados para agregação
        self.data_buffer = deque(maxlen=100)
        self.aggregation_interval = 30  # Segundos entre envios para cloud
        self.last_aggregation_time = time.time()
        
        # Configurações de segurança
        self.username = os.getenv("USER_FOG","")
        self.password = os.getenv("PASSWORD_FOG","")
        
        # Inicializar cliente MQTT
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        
        # Conectar à nuvem e obter token
        self.connect_to_cloud()

    def connect_to_cloud(self):
        try:
            logger.info("Conectando à Cloud API...")
            response = requests.post(
                self.login_url,
                auth=(self.username, self.password),
                timeout=10,
                verify=False  # Importante para evitar erros de SSL
            )
            
            if response.status_code == 200:
                self.auth_token = response.json()['token']
                try:
                    decoded = jwt.decode(self.auth_token, options={"verify_signature": False})
                    self.token_expiration = decoded['exp']
                    logger.info("Conectado à Cloud API com sucesso")
                    logger.info(f"Token expira em: {time.ctime(self.token_expiration)}")
                except jwt.PyJWTError as e:
                    logger.error(f"Erro ao decodificar token: {e}")
                    self.auth_token = None
            else:
                logger.error(f"Falha na autenticação: {response.status_code} - {response.text}")
                self.auth_token = None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de conexão com a cloud: {e}")
            self.auth_token = None
        except Exception as e:
            logger.error(f"Erro inesperado: {e}")
            self.auth_token = None

    def check_token_validity(self):
        """Verifica se o token JWT ainda é válido e renova se necessário"""
        current_time = time.time()
        
        if not self.auth_token or current_time > self.token_expiration - 300:  # Renovar 5 min antes
            logger.warning("Token expirado ou prestes a expirar, renovando...")
            self.connect_to_cloud()
            return self.auth_token is not None
        return True

    def on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("Conectado ao broker MQTT")
            self.mqtt_client.subscribe(self.mqtt_topic_sensors)
            logger.info(f"Inscrito no tópico: {self.mqtt_topic_sensors}")
        else:
            logger.error(f"Falha na conexão MQTT, código: {rc}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            data['received_at'] = time.time()
            data['source'] = msg.topic
            
            logger.info(f"Mensagem MQTT recebida: {data}")
            
            # Adicionar ao buffer para agregação
            self.data_buffer.append(data)
            
            # Análise local na camada Fog
            self.local_analysis(data)
            
            # Verificar se é hora de agregar e enviar para cloud
            current_time = time.time()
            if current_time - self.last_aggregation_time >= self.aggregation_interval:
                if self.data_buffer:  # Só enviar se houver dados
                    self.aggregate_and_send_to_cloud()
                self.last_aggregation_time = current_time
                
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao decodificar JSON MQTT: {e}")
        except Exception as e:
            logger.error(f"Erro ao processar mensagem MQTT: {e}")

    def local_analysis(self, data):
        try:
            # Detecção de padrões regionais
            if 'temperature' in data and data['temperature'] > 37:
                logger.warning(f"Alerta Regional: Temperatura elevada detectada ({data['temperature']}°C)")
                
            # Se vibração excessiva for detectada em múltiplos dispositivos
            vibration_readings = [d.get('vibration', 0) for d in list(self.data_buffer)[-5:] 
                                if 'vibration' in d and d.get('vibration') is not None]
            
            if vibration_readings and len(vibration_readings) >= 3:
                avg_vibration = statistics.mean(vibration_readings)
                if avg_vibration > 7:
                    logger.warning("Alerta Regional: Vibração excessiva em múltiplos dispositivos")
                    logger.info(f"Média de vibração: {avg_vibration:.2f}")
                    
        except Exception as e:
            logger.error(f"Erro na análise local: {e}")

    def aggregate_and_send_to_cloud(self):
        if not self.data_buffer:
            logger.warning("Buffer vazio, nada para enviar")
            return
        
        # Verificar validade do token
        if not self.check_token_validity():
            logger.error("Token inválido, não é possível enviar dados")
            return
        
        try:
            # Agregar dados
            temp_readings = [d.get('temperature') for d in self.data_buffer 
                            if d.get('temperature') is not None]
            vibration_readings = [d.get('vibration') for d in self.data_buffer 
                                if d.get('vibration') is not None]
            presence_readings = [d.get('presence') for d in self.data_buffer 
                                if d.get('presence') is not None]
            
            aggregated_data = {
                "avg_temperature": statistics.mean(temp_readings) if temp_readings else 0,
                "max_temperature": max(temp_readings) if temp_readings else 0,
                "min_temperature": min(temp_readings) if temp_readings else 0,
                "avg_vibration": statistics.mean(vibration_readings) if vibration_readings else 0,
                "presence_count": sum(presence_readings) if presence_readings else 0,
                "samples_count": len(self.data_buffer),
                "timestamp": time.time(),
                "region": "south_zone"
            }
            
            logger.info(f"Dados agregados: {aggregated_data}")
            
            # Enviar para cloud
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                self.cloud_api_url,
                json=aggregated_data,
                headers=headers,
                timeout=10,
                verify=False  # Importante para desenvolvimento
            )
            
            if response.status_code == 200:
                logger.info("Dados enviados com sucesso para a cloud")
                logger.debug(f"Resposta: {response.json()}")
                self.data_buffer.clear()  # Limpar buffer após envio bem-sucedido
            elif response.status_code == 401:
                logger.error("Token inválido ou expirado")
                self.auth_token = None  # Forçar renovação do token
            else:
                logger.error(f"Erro ao enviar para cloud: {response.status_code} - {response.text}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de rede ao enviar para cloud: {e}")
        except Exception as e:
            logger.error(f"Erro inesperado ao enviar para cloud: {e}")

    def send_actuator_command(self, command):
        try:
            self.mqtt_client.publish(
                self.mqtt_topic_actuator,
                json.dumps(command)
            )
            logger.info(f"Comando enviado para atuadores: {command}")
        except Exception as e:
            logger.error(f"Erro ao enviar comando MQTT: {e}")

    def start(self):
        try:
            logger.info("Iniciando nó Fog...")
            
            # Conectar ao MQTT
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port)
            self.mqtt_client.loop_start()
            
            logger.info("Nó Fog iniciado com sucesso")
            logger.info("Estatísticas:")
            logger.info(f"Broker MQTT: {self.mqtt_broker}:{self.mqtt_port}")
            logger.info(f"API Cloud: {self.cloud_api_url}")
            logger.info(f"Intervalo de agregação: {self.aggregation_interval}s")
            
            # Manter o serviço rodando
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Parando nó Fog...")
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            logger.info("Nó Fog parado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao iniciar nó Fog: {e}")

# Script principal
if __name__ == "__main__":
    fog_node = FogNode()
    fog_node.start()