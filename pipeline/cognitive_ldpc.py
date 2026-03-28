import numpy as np
import pyldpc
import time

def simulate_deep_space_transmission(storm_probability: float):
    # Adaptive Cognitive Logic
    if storm_probability < 30.0:
        mode = 'Yüksek Hız (High Speed)'
        snr = 8.0  # Clear channel
        d_v, d_c = 2, 4  # Low redundancy
    elif storm_probability < 75.0:
        mode = 'Dengeli (Balanced)'
        snr = 4.0  # Moderate noise
        d_v, d_c = 3, 6  # Medium redundancy
    else:
        mode = 'Hayatta Kalma (Survival)'
        snr = 1.0  # Severe solar storm noise
        d_v, d_c = 4, 8  # Maximum redundancy

    n = 240  # Block length (LCM of 4, 6, 8 is 24. 240 is perfectly divisible by all d_c states)
    start_time = time.time()
    
    try:
        # 1. Generate LDPC Matrices
        H, G = pyldpc.make_ldpc(n, d_v, d_c, systematic=True, sparse=True)
        k = G.shape[1]
        
        # 2. Generate Payload (Mars Rover Data Simulation)
        original_msg = np.random.randint(2, size=k)
        
        # 3. Encode & Transmit through Solar Storm (AWGN Channel)
        noisy_signal = pyldpc.encode(G, original_msg, snr)
        
        # Calculate raw bit errors in transit
        transmitted_bits = np.where(noisy_signal >= 0, 1, 0)
        corrupted_bits = np.sum(original_msg != transmitted_bits[:k])
        
        # 4. Decode & Correct Errors
        decoded_signal = pyldpc.decode(H, noisy_signal, snr, maxiter=100)
        recovered_msg = pyldpc.get_message(G, decoded_signal)
        
        # 5. Validation
        final_errors = np.sum(abs(original_msg - recovered_msg))
        success_rate = 100.0 if final_errors == 0 else ((k - final_errors) / k) * 100
        
    except Exception as e:
        return {'error': str(e)}

    return {
        'mode': mode,
        'snr': snr,
        'redundancy_ratio': f'{k}/{n}',
        'corrupted_bits': int(corrupted_bits),
        'recovered_100_percent': bool(final_errors == 0),
        'success_rate': success_rate,
        'calc_time': round(time.time() - start_time, 2)
    }
