from flask import Flask, render_template_string
import os
import pandas as pd

app = Flask(__name__)
RESULTS_FOLDER = 'Results'

# Mapeo: columnas del CSV (en inglés) → nombres mostrados (en español)
MAPEO_EMOCIONES = {
    "Anger": "Enojo",
    "Disgust": "Disgusto",
    "Fear": "Miedo",
    "Joy": "Felicidad",
    "Sadness": "Tristeza",
    "Surprise": "Sorpresa",
    "Neutral": "Neutral",
    "Anticipation": "Anticipación",
    "Trust": "Confianza",
    "Love": "Amor",
    "Submission": "Sumisión",
    "Awe": "Asombro",
    "Disapproval": "Desaprobación",
    "Remorse": "Remordimiento",
    "Contempt": "Desdén",
    "Agressiveness": "Agresividad",
    "Optimism": "Optimismo",
    "Guilt": "Culpa",
    "Curiosity": "Curiosidad",
    "Despair": "Desesperación",
    "Unbelief": "Incredulidad",
    "Envy": "Envidia",
    "Cynicism": "Cinismo",
    "Pride": "Orgullo",
    "Hope": "Esperanza",
    "Delight": "Deleite",
    "Sentimentality": "Sentimentalismo",
    "Shame": "Vergüenza",
    "Outrage": "Escándalo",
    "Pessimism": "Pesimismo",
    "Morbidness": "Morbosidad",
    "Dominance": "Dominio",
    "Anxiety": "Ansiedad",
    "Stress": "Estrés",
    "Stress_intens": "Estrés intenso",
    "Cognitive effort": "Esfuerzo Cognitivo",
    "Frustration": "Frustración",
    "Interest": "Interés",
    "Rejection": "Rechazo",
    "Commitment": "Compromiso",
    "Confusion": "Confusión",
    "Comprehension": "Comprensión",
    "Performance": "Desempeño",
    "Confidence 1": "Confianza 1",
    "Confidence 2": "Confianza 2"
}

@app.route('/')
def index():
    archivos = [f for f in os.listdir(RESULTS_FOLDER) if f.endswith('.csv')]
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Explorador de CSV local</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4faff; font-family: 'Segoe UI', sans-serif; }
        .container { margin-top: 60px; }
        h1 { text-align: center; margin-bottom: 30px; }
        .file-list a { text-decoration: none; color: #007bff; font-weight: 500; }
        .file-list a:hover { text-decoration: underline; }
    </style>
</head>
<body>
<div class="container">
    <h1>📁 Archivos CSV en carpeta 'Results'</h1>
    <ul class="list-group file-list">
    {% for file in archivos %}
        <li class="list-group-item">
            📄 <a href="{{ url_for('ver_csv', nombre=file) }}">{{ file }}</a>
        </li>
    {% endfor %}
    </ul>
</div>
</body>
</html>
""", archivos=archivos)

@app.route('/csv/<nombre>')
@app.route('/csv/<nombre>')
def ver_csv(nombre):
    filepath = os.path.join(RESULTS_FOLDER, nombre)
    if not os.path.isfile(filepath) or not nombre.endswith('.csv'):
        return "Archivo no encontrado", 404

    df = pd.read_csv(filepath)
    # Resumen de valencias en español
    valence_mapeo = {
        "Positive valence": "Valencia positiva",
        "Negative valence": "Valencia negativa",
        "Intensity": "Intensidad emocional"
    }

    valence_stats = []
    for col, label in valence_mapeo.items():
        if col in df.columns:
            valence_stats.append(f"{label}: {df[col].mean():.4f}")
    valence_text = " | ".join(valence_stats)

    # Tabla 1: Promedios de emociones
    emocion_data = []
    total_promedio_emociones = 0

    for col_eng, col_esp in MAPEO_EMOCIONES.items():
        if col_eng in df.columns:
            promedio = df[col_eng].mean()
            emocion_data.append({'emoción': col_esp, 'promedio': promedio})
            total_promedio_emociones += promedio

    for e in emocion_data:
        e['porcentaje'] = (e['promedio'] / total_promedio_emociones * 100) if total_promedio_emociones > 0 else 0

    # Tabla 2: Frecuencia Predominant
    pred_data = []
    if 'Predominant' in df.columns:
        total_pred = len(df)
        conteo = df['Predominant'].value_counts()
        for emocion_eng, valor in conteo.items():
            emocion_esp = MAPEO_EMOCIONES.get(emocion_eng, emocion_eng)
            pred_data.append({
                'emoción': emocion_esp,
                'valor': valor,
                'porcentaje': (valor / total_pred) * 100
            })

    # Tabla 3: Frecuencia Trend
    trend_data = []
    if 'Trend' in df.columns:
        total_trend = len(df)
        conteo_trend = df['Trend'].value_counts()
        for emocion_eng, valor in conteo_trend.items():
            emocion_esp = MAPEO_EMOCIONES.get(emocion_eng, emocion_eng)
            trend_data.append({
                'emoción': emocion_esp,
                'valor': valor,
                'porcentaje': (valor / total_trend) * 100
            })

    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>{{ nombre }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.datatables.net/1.13.4/css/dataTables.bootstrap5.min.css" rel="stylesheet">
    <style>
        body { background-color: #fcfcfc; padding: 40px; }
        .table-container { max-width: 95%; margin: auto; }
        h2 { text-align: center; margin-bottom: 25px; }
        .small-table { font-size: 0.9rem; }
        .table-row { display: flex; gap: 30px; justify-content: center; flex-wrap: wrap; }
        .table-box { width: 600px; }
        body {
            background-color: #222;
            color: #fff;
        }
    </style>
</head>
<body>
    <div class="table-container">
        <h2>📊 Análisis emocional — {{ nombre }}</h2>
        <div class="mb-5 text-center">

        </div>
        <h6 style="text-align:center; margin-bottom: 30px; color: #555;">
            {{ valence_text }}
        </h6>
        <div class="table-row">
            <div class="table-box">
                <h5>Resumen por promedio</h5>
                <table id="tabla-emociones" class="table table-bordered small-table">
                    <thead class="table-light">
                        <tr>
                            <th>Emoción</th>
                            <th>Promedio</th>
                            <th>% sobre total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for e in emocion_data %}
                        <tr>
                            <td>{{ e.emoción }}</td>
                            <td>{{ '%.4f' % e.promedio }}</td>
                            <td>{{ '%.2f' % e.porcentaje }}%</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>

            <div class="table-box">
                <h5>Frecuencia de emoción predominante</h5>
                <table id="tabla-predominant" class="table table-bordered small-table">
                    <thead class="table-light">
                        <tr>
                            <th>Emoción</th>
                            <th>Valor</th>
                            <th>% sobre total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for p in pred_data %}
                        <tr>
                            <td>{{ p.emoción }}</td>
                            <td>{{ p.valor }}</td>
                            <td>{{ '%.2f' % p.porcentaje }}%</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>

            <div class="table-box">
                <h5>Frecuencia de emoción en tendencia</h5>
                <table id="tabla-trend" class="table table-bordered small-table">
                    <thead class="table-light">
                        <tr>
                            <th>Emoción</th>
                            <th>Valor</th>
                            <th>% sobre total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for t in trend_data %}
                        <tr>
                            <td>{{ t.emoción }}</td>
                            <td>{{ t.valor }}</td>
                            <td>{{ '%.2f' % t.porcentaje }}%</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <hr>
        <h2>📄 Contenido completo del archivo</h2>
        

        <br><a href="/" class="btn btn-secondary">← Regresar</a>
    </div>

    <!-- DataTables JS -->
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.4/js/dataTables.bootstrap5.min.js"></script>
    <script>
        $(document).ready(function () {
            $('#tabla-emociones').DataTable({
                paging: false,
                searching: false,
                info: false,
                order: [[1, 'desc']]
            });
            $('#tabla-predominant').DataTable({
                paging: false,
                searching: false,
                info: false,
                order: [[1, 'desc']]
            });
            $('#tabla-trend').DataTable({
                paging: false,
                searching: false,
                info: false,
                order: [[1, 'desc']]
            });
        });
    </script>
<!-- Chart.js -->
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
    const radarLabels = {{ emocion_data|map(attribute='emoción')|list|tojson }};
    const radarValues = {{ emocion_data|map(attribute='porcentaje')|list|tojson }};

    const ctx = document.getElementById('radarChart').getContext('2d');
    new Chart(ctx, {
        type: 'radar',
        data: {
            labels: radarLabels,
            datasets: [{
                label: 'Emoción Compleja (%)',
                data: radarValues,
                fill: true,
                borderColor: 'rgba(0, 153, 255, 0.8)',
                backgroundColor: 'rgba(0, 153, 255, 0.2)',
                pointBackgroundColor: 'rgba(0, 153, 255, 1)',
                pointBorderColor: '#fff',
                pointHoverBackgroundColor: '#fff',
                pointHoverBorderColor: 'rgba(0, 153, 255, 1)'
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: 'Emoción Compleja',
                    color: '#fff',
                    padding: { top: 10, bottom: 10 },
                    font: { size: 18 }
                },
                legend: {
                    labels: { color: '#fff' }
                }
            },
            scales: {
                r: {
                    pointLabels: {
                        color: '#fff',
                        font: { size: 10 }
                    },
                    ticks: {
                        color: '#ccc',
                        backdropColor: 'transparent',
                        beginAtZero: true
                    },
                    grid: { color: 'rgba(255,255,255,0.2)' },
                    angleLines: { color: 'rgba(255,255,255,0.3)' }
                }
            }
        }
    });
</script>
</body>
</html>
""", nombre=nombre,
       table=df.to_html(classes='table table-striped table-bordered', index=False),
       emocion_data=emocion_data,
       pred_data=pred_data,
       trend_data=trend_data,
       valence_text=valence_text)


if __name__ == '__main__':
    app.run(debug=True, port=5002)
