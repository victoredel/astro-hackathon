import random

def calculate_terrestrial_impact(storm_probability: float):
    # 1. Simular parámetros físicos de la tormenta basados en la probabilidad de la IA
    if storm_probability < 30.0:
        bz_component = random.uniform(0, 10)  # Apunta al Norte (Seguro)
        solar_wind_speed = random.uniform(300, 450) # km/s
        kp_index = random.randint(1, 3)
    elif storm_probability < 75.0:
        bz_component = random.uniform(-5, 5)  # Fluctuante
        solar_wind_speed = random.uniform(450, 700)
        kp_index = random.randint(4, 6)
    else:
        bz_component = random.uniform(-25, -10) # Apunta al Sur (Peligro crítico de reconexión magnética)
        solar_wind_speed = random.uniform(800, 2000)
        kp_index = random.randint(7, 9)

    # 2. Factor de Latitud para Turquía (aprox 39° N)
    # Las latitudes medias sufren menos que los polos, requiere un Kp alto para impacto severo.
    turkey_latitude_factor = 0.6 if kp_index < 8 else 0.95 

    # 3. Calcular Probabilidad de Daño Terrestre (GIC Risk)
    # Si Bz es positivo, el escudo terrestre protege la red, bajando drásticamente el riesgo.
    if bz_component > 0:
        terrestrial_risk = storm_probability * 0.2 
    else:
        terrestrial_risk = storm_probability * turkey_latitude_factor * (abs(bz_component) / 10)

    # Limitar a 100%
    terrestrial_risk = min(terrestrial_risk, 99.9)
    
    # 4. Decisión de TEİAŞ (Red Eléctrica)
    action_required = "GÜVENLİ (Seguro)"
    if terrestrial_risk > 80.0:
        action_required = "KRİTİK: Trafo merkezlerini şebekeden ayırın (Desconectar subestaciones)"
        gic_amps = random.uniform(100, 300) # Amperios inducidos
    elif terrestrial_risk > 50.0:
        action_required = "UYARI: Jeneratörleri hazırda bekletin (Preparar generadores)"
        gic_amps = random.uniform(30, 90)
    else:
        action_required = "NORMAL İŞLETİM (Operación Normal)"
        gic_amps = random.uniform(0, 15)

    return {
        "spatial_prob": round(storm_probability, 1),
        "terrestrial_risk": round(terrestrial_risk, 1),
        "bz_component": round(bz_component, 1),
        "kp_index": kp_index,
        "solar_wind_speed": int(solar_wind_speed),
        "action_required": action_required,
        "gic_amps": int(gic_amps)
    }
