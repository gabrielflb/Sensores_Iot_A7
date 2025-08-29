from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import jwt
import datetime
from functools import wraps
import os
from collections import deque
import numpy as np
from sklearn.linear_model import LinearRegression
from dotenv import load_dotenv
import threading

load_dotenv()

try:    
    app = Flask(__name__)
    CORS(app)
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "")
except:
    input("erro ao configurar chave")    

# Simulação de banco de dados em memória
try:
    data_history = deque(maxlen=100)  # Mantém últimos 100 registros
    alert_history = []
    users = {
        "fog_node": os.getenv("FOG_NODE",""),
        "admin": os.getenv("ADMIN","")
    }
except:
    input("Erro ao iniciar banco em memoria")

# Modelo para previsão de temperatura
temp_prediction_model = LinearRegression()
temp_data = deque(maxlen=20)
prediction_lock = threading.Lock()

# Decorator para verificar token JWT
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token de acesso é necessário!'}), 401
        
        try:
            # Remove o prefixo 'Bearer ' se presente
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data['user']
        except:
            return jsonify({'message': 'Token é inválido ou expirou!'}), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

# Rota para login e obtenção de token
@app.route('/api/login', methods=['POST'])
def login():
    auth = request.authorization
    if not auth or not auth.username or not auth.password:
        return jsonify({'message': 'Credenciais não fornecidas!'}), 401
    
    if auth.username in users and users[auth.username] == auth.password:
        token = jwt.encode({
            'user': auth.username,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        
        return jsonify({'token': token})
    
    return jsonify({'message': 'Login inválido!'}), 401

# Rota para receber dados da camada Fog
@app.route('/api/data', methods=['POST'])
@token_required
def receive_data(current_user):
    if not request.is_json:
        return jsonify({"error": "Dados devem estar em formato JSON"}), 400
    
    data = request.get_json()
    
    # Validação básica dos dados
    if data is None or 'avg_temperature' not in data:
        return jsonify({"error": "Campo 'avg_temperature' é obrigatório"}), 400
    
    # Adiciona timestamp
    data['timestamp'] = datetime.datetime.now().isoformat()
    data['node'] = current_user
    
    # Adiciona aos históricos
    data_history.append(data)
    
    # Atualiza modelo de previsão
    with prediction_lock:
        if 'avg_temperature' in data and data['avg_temperature'] is not None:
            temp_data.append(data['avg_temperature'])
            if len(temp_data) > 5:
                try:
                    X = np.arange(len(temp_data)).reshape(-1, 1)
                    y = np.array(temp_data)
                    temp_prediction_model.fit(X, y)
                except Exception as e:
                    print(f"Erro no treinamento do modelo: {e}")
    
    if 'avg_temperature' in data and data['avg_temperature'] is not None:
        temp_value = data['avg_temperature']
        
        if temp_value > 38:
            alert = {
                'type': 'high_temperature',
                'message': f'Temperatura crítica detectada: {temp_value:.2f}°C',
                'timestamp': data['timestamp'],
                'severity': 'high',
                'value': temp_value
            }
            alert_history.append(alert)
            print(f"Alerta: {alert['message']}")
        
        elif temp_value > 35:
            alert = {
                'type': 'warning_temperature',
                'message': f'Temperatura elevada: {temp_value:.2f}°C',
                'timestamp': data['timestamp'],
                'severity': 'warning',
                'value': temp_value
            }
            alert_history.append(alert)
            print(f"Alerta: {alert['message']}")
    
    return jsonify({"status": "success", "message": "Dados recebidos"}), 200

# Rota para obter histórico de dados
@app.route('/api/history', methods=['GET'])
@token_required
def get_history(current_user):
    limit = request.args.get('limit', default=50, type=int)
    return jsonify(list(data_history)[-limit:])

# Rota para obter alertas
@app.route('/api/alerts', methods=['GET'])
@token_required
def get_alerts(current_user):
    limit = request.args.get('limit', default=10, type=int)
    return jsonify(list(alert_history)[-limit:])

# Rota para previsão de temperatura
@app.route('/api/predict/temperature', methods=['GET'])
@token_required
def predict_temperature(current_user):
    with prediction_lock:
        if len(temp_data) < 5:
            return jsonify({"error": "Dados insuficientes para previsão"}), 400
        
        # Prever próximos 3 valores
        future_X = np.arange(len(temp_data), len(temp_data) + 3).reshape(-1, 1)
        predictions = temp_prediction_model.predict(future_X)
        
        # Verificar se há tendência de superaquecimento
        overheating_risk = any(pred > 38 for pred in predictions)
        
        return jsonify({
            "predictions": predictions.tolist(),
            "overheating_risk": overheating_risk,
            "timestamp": datetime.datetime.now().isoformat()
        })

# Rota para status do sistema
@app.route('/api/status', methods=['GET'])
@token_required
def get_status(current_user):
    try:
        last_data = data_history[-1] if data_history else {}
        
        # Contar alertas por severidade
        high_alerts = len([a for a in alert_history if a.get('severity') == 'high'])
        warning_alerts = len([a for a in alert_history if a.get('severity') == 'warning'])
        total_alerts = len(alert_history)
        
        return jsonify({
            "status": "operational",
            "data_points": len(data_history),
            "alerts": total_alerts,
            "high_alerts": high_alerts,
            "warning_alerts": warning_alerts,
            "last_update": last_data.get('timestamp', "N/A"),
            "current_temperature": last_data.get('avg_temperature', "N/A")
        })
    except Exception as e:
        print(f"Erro no endpoint de status: {e}")
        return jsonify({"error": "Erro interno"}), 500

# Rota principal da documentação da API
@app.route('/api/docs')
def api_docs():
    return render_template('/frontend/docs/api_docs.html')

# Dashboard principal
@app.route('/dashboard')
def dashboard():
    return render_template('/frontend/dashboard.html')

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
        input("Pressione ENTER para sair...")
    except:
        print
    
    
    
