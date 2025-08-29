        const API_BASE_URL = 'http://localhost:5000'; // ✅ URL absoluta com HTTP
        let authToken = null;
        let tempChart = null;
        let updateInterval = null;

        // Elementos DOM
        const elements = {
            systemStatus: document.getElementById('system-status-text'),
            currentTemp: document.getElementById('current-temp'),
            alertsCount: document.getElementById('alerts-count'),
            dataPoints: document.getElementById('data-points'),
            statusDetails: document.getElementById('status-details'),
            alertsList: document.getElementById('alerts-list'),
            tempChart: document.getElementById('tempChart')
        };

        // Função para mostrar erro
        function showError(element, message) {
            element.innerHTML = `<div class="error">❌ ${message}</div>`;
        }

        // Função de login
        async function login() {
            try {
                console.log('Tentando login...');
                
                const response = await fetch(`${API_BASE_URL}/api/login`, {
                    method: 'POST',
                    headers: {
                        'Authorization': 'Basic ' + btoa('fog_node:fog_password_123'),
                        'Content-Type': 'application/json'
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();
                
                if (data.token) {
                    authToken = data.token;
                    console.log('Login realizado com sucesso');
                    return true;
                } else {
                    throw new Error('Token não recebido');
                }
                
            } catch (error) {
                console.error('Erro no login:', error);
                showError(elements.systemStatus, `Erro de autenticação: ${error.message}`);
                return false;
            }
        }

        // Função para fazer requisições autenticadas
        async function makeAuthenticatedRequest(url, options = {}) {
            if (!authToken) {
                const loggedIn = await login();
                if (!loggedIn) {
                    throw new Error('Não autenticado');
                }
            }

            const defaultOptions = {
                headers: {
                    'Authorization': `Bearer ${authToken}`,
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            };

            const mergedOptions = { ...defaultOptions, ...options };
            
            try {
                const response = await fetch(url, mergedOptions);
                
                // Se token expirou, tentar renovar
                if (response.status === 401) {
                    console.log('Token expirado, renovando...');
                    const loggedIn = await login();
                    if (loggedIn) {
                        mergedOptions.headers['Authorization'] = `Bearer ${authToken}`;
                        return await fetch(url, mergedOptions);
                    }
                }
                
                return response;
            } catch (error) {
                console.error('Erro na requisição:', error);
                throw error;
            }
        }

        // Atualizar status do sistema
        async function updateSystemStatus() {
            try {
                const response = await makeAuthenticatedRequest(`${API_BASE_URL}/api/status`);
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();
                
                elements.systemStatus.innerHTML = `
                    <span class="status-indicator status-online"></span>
                    Sistema Operacional
                `;
                
                elements.currentTemp.textContent = `${data.current_temperature.toFixed(2)}°C`;
                elements.alertsCount.textContent = data.alerts;
                console.log(data.alerts);
                elements.dataPoints.textContent = data.data_points;
                
                elements.statusDetails.innerHTML = `
                    <small>Última atualização: ${new Date(data.last_update).toLocaleTimeString()}</small>
                `;
                
            } catch (error) {
                console.error('Erro ao atualizar status:', error);
                elements.systemStatus.innerHTML = `
                    <span class="status-indicator status-offline"></span>
                    Sistema Offline
                `;
            }
        }

        // Atualizar gráfico de temperatura
        async function updateChart() {
            try {
                const response = await makeAuthenticatedRequest(`${API_BASE_URL}/api/history?limit=20`);
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const history = await response.json();
                
                if (history.length === 0) {
                    return;
                }

                const labels = history.map(item => 
                    new Date(item.timestamp).toLocaleTimeString()
                );
                
                const temperatures = history.map(item => item.avg_temperature);

                const ctx = elements.tempChart.getContext('2d');
                
                if (tempChart) {
                    tempChart.data.labels = labels;
                    tempChart.data.datasets[0].data = temperatures;
                    tempChart.update();
                } else {
                    tempChart = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [{
                                label: 'Temperatura Média (°C)',
                                data: temperatures,
                                borderColor: 'rgb(75, 192, 192)',
                                backgroundColor: 'rgba(75, 192, 192, 0.1)',
                                tension: 0.4,
                                fill: true,
                                pointBackgroundColor: 'rgb(75, 192, 192)',
                                pointBorderColor: '#fff',
                                pointRadius: 5,
                                pointHoverRadius: 8
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: {
                                    display: true,
                                    position: 'top'
                                },
                                tooltip: {
                                    mode: 'index',
                                    intersect: false
                                }
                            },
                            scales: {
                                y: {
                                    suggestedMin: 20,
                                    suggestedMax: 45,
                                    grid: {
                                        color: 'rgba(0, 0, 0, 0.1)'
                                    }
                                },
                                x: {
                                    grid: {
                                        color: 'rgba(0, 0, 0, 0.1)'
                                    }
                                }
                            },
                            animation: {
                                duration: 1000,
                                easing: 'easeOutQuart'
                            }
                        }
                    });
                }
                
            } catch (error) {
                console.error('Erro ao atualizar gráfico:', error);
            }
        }

        // Atualizar alertas
        async function updateAlerts() {
            try {
                const response = await makeAuthenticatedRequest(`${API_BASE_URL}/api/alerts?limit=5`);
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const alerts = await response.json();
                
                if (alerts.length === 0) {
                    elements.alertsList.innerHTML = '<div class="alert alert-info">✅ Nenhum alerta recente</div>';
                    return;
                }

                let alertsHTML = '';
                alerts.forEach(alert => {
                    const alertClass = alert.severity === 'high' ? 'alert-high' : 
                                     alert.severity === 'warning' ? 'alert-warning' : 'alert-info';
                    
                    alertsHTML += `
                        <div class="alert ${alertClass}">
                            <strong>${alert.type === 'high_temperature' ? 'Temperatura Alta' : ' ' + alert.type}</strong>
                            <p>${alert.message}</p>
                            <small>${new Date(alert.timestamp).toLocaleString()}</small>
                        </div>
                    `;
                });
                
                elements.alertsList.innerHTML = alertsHTML;
                
            } catch (error) {
                console.error('Erro ao atualizar alertas:', error);
                showError(elements.alertsList, `Erro ao carregar alertas: ${error.message}`);
            }
        }

        // Inicializar dashboard
        async function initializeDashboard() {
            console.log('Inicializando dashboard...');
            
            // Fazer login primeiro
            const loggedIn = await login();
            
            if (loggedIn) {
                // Atualizar dados imediatamente
                await updateSystemStatus();
                await updateChart();
                await updateAlerts();
                
                // Configurar atualização periódica
                updateInterval = setInterval(async () => {
                    await updateSystemStatus();
                    await updateChart();
                    await updateAlerts();
                }, 5000); // Atualizar a cada 5 segundos
                
                console.log('Dashboard inicializado com sucesso');
            } else {
                showError(elements.systemStatus, 'Falha na inicialização. Verifique o servidor.');
            }
        }

        // Iniciar quando a página carregar
        document.addEventListener('DOMContentLoaded', initializeDashboard);

        // Limpar intervalo quando a página for fechada
        window.addEventListener('beforeunload', () => {
            if (updateInterval) {
                clearInterval(updateInterval);
            }
        });