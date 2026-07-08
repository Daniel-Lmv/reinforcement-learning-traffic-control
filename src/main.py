import os
import sys
import torch
import numpy as np
import random
import traci  # Interface de comunicação com o SUMO

MAX_FILA = 30
MAX_TEMPO = 60
STATE_DIM = 5
ACTION_DIM = 5

ID_SEMAFORO = "clusterJ13_J15" 

# Arquitetura da Rede Neural
class QNetwork(torch.nn.Module):
    def __init__(self, state_dim, action_dim):
        super(QNetwork, self).__init__()
        self.fc = torch.nn.Sequential(
            torch.nn.Linear(state_dim, 128),
            torch.nn.ReLU(),
            torch.nn.Linear(128, 128),
            torch.nn.ReLU(),
            torch.nn.Linear(128, action_dim)
        )
    def forward(self, x):
        return self.fc(x)

def normalizar_estado(state):
    fila_NS, fila_LO, tempo_V, fase_atual, tempo_desde_troca = state
    return np.array([
        fila_NS / MAX_FILA,
        fila_LO / MAX_FILA,
        tempo_V / MAX_TEMPO,
        float(fase_atual),
        min(1.0, tempo_desde_troca / 20.0)
    ], dtype=np.float32)

# CARREGAMENTO DO MODELO
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
policy_net = QNetwork(STATE_DIM, ACTION_DIM).to(device)
policy_net.load_state_dict(torch.load("best_traffic_dqn.pt", map_location=device))
policy_net.eval()

# INICIALIZAÇÃO DO SUMO
sumo_cmd = ["sumo-gui", "-c", "teste.sumocfg"]
traci.start(sumo_cmd)

fase_atual = 0  # No treino: 0 = NS Verde, 1 = LO Verde
tempo_V = 25    
tempo_desde_troca = 10

print("=> Integração Concluída. Inteligência Artificial comandando o clusterJ13_J15!")

step_count = 0
try:
    while traci.simulation.getMinExpectedNumber() > 0:
        
        # 1. Contagem exata de carros parados
        fila_NS = (traci.lane.getLastStepHaltingNumber("lane_N_to_S_0") + 
                   traci.lane.getLastStepHaltingNumber("lane_S_to_N_0"))
                   
        fila_LO = (traci.lane.getLastStepHaltingNumber("lane_L_to_O_0") + 
                   traci.lane.getLastStepHaltingNumber("lane_O_to_L_0"))
        
        # 2. Processamento do Estado para a IA
        estado_bruto = [fila_NS, fila_LO, tempo_V, fase_atual, tempo_desde_troca]
        estado_norm = normalizar_estado(estado_bruto)
        estado_t = torch.FloatTensor(estado_norm).to(device).unsqueeze(0)
        
        # 3. Inferência da Política Ótima
        with torch.no_grad():
            action = policy_net(estado_t).argmax(1).item()
            
        # 4. Atuação Inteligente no Semáforo do SUMO
        if action == 1 and fase_atual != 0:
            fase_atual = 0
            tempo_desde_troca = 0
            traci.trafficlight.setPhase(ID_SEMAFORO, 2) 
        elif action == 2 and fase_atual != 1:
            fase_atual = 1
            tempo_desde_troca = 0
            traci.trafficlight.setPhase(ID_SEMAFORO, 0)
        elif action == 3:
            tempo_V = min(MAX_TEMPO, tempo_V + 5)
        elif action == 4:
            tempo_V = max(10, tempo_V - 5)
        else:
            tempo_desde_troca += 1
            
        traci.simulationStep()
        step_count += 1
        
        if step_count % 10 == 0:
            direcao = "Norte-Sul" if fase_atual == 0 else "Leste-Oeste"
            print(f"Tempo: {step_count}s | Filas (NS/LO): {fila_NS}/{fila_LO} | Sinal Ativo: {direcao} | Ação: {action}")

except Exception as e:
    print(f"Interrupção na execução: {e}")

finally:
    traci.close()
    print("=> Simulação finalizada.")