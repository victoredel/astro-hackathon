import numpy as np
import pyldpc
import time

def simulate_deep_space_transmission(storm_probability: float):
    # Paquete de 1 MB = 8,388,608 bits
    PAYLOAD_BITS = 8388608
    BASE_SPEED_MBPS = 10.0 # Velocidad bruta teórica del enlace (10 Mbps)

    # Lógica Cognitiva y Adaptativa
    if storm_probability < 30.0:
        mode = 'Yüksek Hız (Hız Öncelikli)' # Alta Velocidad
        icon = '⚡'
        snr = 8.0  # Canal limpio
        # dv=2, dc=8 -> Redundancia: 1 - 2/8 = 0.75 (75% Datos, 25% Escudo Paridad)
        d_v, d_c = 2, 8  
    elif storm_probability < 75.0:
        mode = 'Dengeli (Optimum)' # Equilibrado
        icon = '⚖️'
        snr = 4.0  # Ruido moderado
        # dv=3, dc=6 -> Redundancia: 1 - 3/6 = 0.50 (50% Datos, 50% Escudo)
        d_v, d_c = 3, 6  
    else:
        mode = 'Zırh (Güvenlik Öncelikli)' # Armadura / Supervivencia
        icon = '🛡️'
        snr = 1.0  # Tormenta solar severa (mucho ruido)
        # dv=4, dc=5 -> Redundancia: 1 - 4/5 = 0.20 (20% Datos, 80% Escudo)
        d_v, d_c = 4, 5  

    n = 240  # Tamaño del bloque para la simulación rápida
    start_time = time.time()
    
    try:
        # 1. Generar Matrices LDPC
        H, G = pyldpc.make_ldpc(n, d_v, d_c, systematic=True, sparse=True)
        k = G.shape[1]
        
        # Ratio de eficiencia (Cuánta porción del ancho de banda son datos reales)
        data_ratio = k / n
        
        # 2. Simulación con un bloque pequeño (para evitar que Streamlit se congele)
        original_msg = np.random.randint(2, size=k)
        noisy_signal = pyldpc.encode(G, original_msg, snr)
        
        transmitted_bits = np.where(noisy_signal >= 0, 1, 0)
        sim_corrupted_bits = np.sum(original_msg != transmitted_bits[:k])
        bit_error_rate = sim_corrupted_bits / k
        
        # 3. Decodificar y reparar
        decoded_signal = pyldpc.decode(H, noisy_signal, snr, maxiter=100)
        recovered_msg = pyldpc.get_message(G, decoded_signal)
        sim_final_errors = np.sum(abs(original_msg - recovered_msg))
        
        # 4. Extrapolar matemáticas para el paquete de 1 MB
        extrapolated_corrupted = int(PAYLOAD_BITS * bit_error_rate)
        effective_speed = BASE_SPEED_MBPS * data_ratio
        
        success_rate = 100.0 if sim_final_errors == 0 else ((k - sim_final_errors) / k) * 100
        
    except Exception as e:
        return {'error': str(e)}

    return {
        'mode': mode,
        'icon': icon,
        'snr': snr,
        'data_ratio_pct': int(data_ratio * 100),
        'effective_speed_mbps': round(effective_speed, 1),
        'extrapolated_corrupted': extrapolated_corrupted,
        'recovered_100_percent': bool(sim_final_errors == 0),
        'success_rate': success_rate,
        'calc_time': round(time.time() - start_time, 2)
    }