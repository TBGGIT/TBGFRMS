from flask import Flask, request, render_template_string, send_file
import psycopg2
from datetime import datetime
import re
import calendar
import os
from datetime import date
from cryptography.fernet import Fernet
import io
import pandas as pd

def load_encrypted_config():
    # Leer la clave
    with open("key.key", "rb") as key_file:
        key = key_file.read()
    fernet = Fernet(key)

    # Leer y desencriptar los datos
    with open("db.txt", "rb") as enc_file:
        encrypted_data = enc_file.read()
    decrypted_data = fernet.decrypt(encrypted_data).decode()

    # Evaluar las variables como si fueran Python code
    config = {}
    exec(decrypted_data, config)
    return config


app = Flask(__name__)

CONFIG = load_encrypted_config()
DB_CONFIG = CONFIG["ODOO_DB_CONFIG"]


ETAPAS_ORDENADAS = [
    "I Funnel",
    "II Prospecto",
    "III Cita Diagnóstico",
    "IV Integración Info",
    "V Propuesta",
    "VI Cierre Comercial",
    "VII Alta Cliente",
    "VIII Inicio Operaciones"
]

# Preprocesar comparadores normalizados
def normalizar_etapa(texto):
    texto = texto.lower().replace(".", "").replace(":", "")
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

COMPARADORES_ETAPAS = {normalizar_etapa(etapa): etapa for etapa in ETAPAS_ORDENADAS}

def get_stage_durations(anio=None, mes=None, fecha_inicio=None, fecha_fin=None):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            l.id AS lead_id,
            l.partner_name,
            l.contact_name,
            l.create_date,
            m.create_date AS stage_date,
            REGEXP_REPLACE(m.body, '<[^>]*>', '', 'g') AS stage_name
        FROM crm_lead l
        LEFT JOIN mail_message m ON m.model = 'crm.lead' AND m.res_id = l.id
        WHERE l.active = TRUE AND m.body ILIKE '%etapa%'
        ORDER BY l.id, stage_date
    """)


    rows = cur.fetchall()
    cur.close()
    conn.close()

    etapas_por_lead = {}
    for row in rows:
        lead_id, empresa, contacto, fecha_creacion, fecha_etapa, stage_body = row
        etapa = "OTRAS"
        clean_body = normalizar_etapa(stage_body or "")

        for comparador_normalizado, etapa_oficial in COMPARADORES_ETAPAS.items():
            if comparador_normalizado in clean_body:
                etapa = etapa_oficial
                break

        if anio and (fecha_etapa is None or fecha_etapa.year != anio):
            continue
        if mes and (fecha_etapa is None or fecha_etapa.month != mes):
            continue
        if fecha_etapa:
            if fecha_inicio and fecha_etapa < fecha_inicio:
                continue
            if fecha_fin and fecha_etapa > fecha_fin:
                continue
        if lead_id not in etapas_por_lead:
            etapas_por_lead[lead_id] = []
        etapas_por_lead[lead_id].append((empresa, contacto, etapa, fecha_etapa))

    etapas_mensuales = []
    for lead_id, etapas in etapas_por_lead.items():
        etapas_ordenadas = sorted(etapas, key=lambda x: x[3])  # por fecha
        for i, etapa_data in enumerate(etapas_ordenadas):
            empresa, contacto, etapa, fecha_actual = etapa_data
            fecha_siguiente = etapas_ordenadas[i + 1][3] if i + 1 < len(etapas_ordenadas) else datetime.now()
            dias = (fecha_siguiente - fecha_actual).days
            fecha_formateada = fecha_actual.strftime("%Y-%m-%d") if fecha_actual else ""
            etapas_mensuales.append((empresa, contacto, etapa, dias, fecha_formateada))

    # Ordenar
    etapas_mensuales.sort(key=lambda x: (x[0] or '', ETAPAS_ORDENADAS.index(x[2]) if x[2] in ETAPAS_ORDENADAS else 999))

    # Alternar color
    colored_data = []
    last_company = None
    current_class = "even"
    for row in etapas_mensuales:
        empresa, contacto, etapa, dias, fecha_formateada = row
        if empresa != last_company:
            current_class = "odd" if current_class == "even" else "even"
            last_company = empresa
        colored_data.append((empresa, contacto, etapa, dias, fecha_formateada, current_class))

    print(f"🔎 Total etapas procesadas: {len(colored_data)}")
    # Contador por etapa
# Contador por etapa con lead único en su última etapa
    contador_etapas = {etapa: 0 for etapa in ETAPAS_ORDENADAS}
    for lead_id, etapas in etapas_por_lead.items():
        etapas_ordenadas = sorted(etapas, key=lambda x: x[3])  # x[3] es fecha
        if etapas_ordenadas:
            _, _, etapa_final, _ = etapas_ordenadas[-1]
            if etapa_final in contador_etapas:
                contador_etapas[etapa_final] += 1
    

    conteo_por_fecha_etapa = {}
    for row in etapas_mensuales:
        _, _, etapa, _, fecha_str = row
        if not fecha_str:
            continue
        fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        year, week_num, _ = fecha_obj.isocalendar()
        semana_label = f"{year}-S{week_num:02d}"

        if etapa not in conteo_por_fecha_etapa:
            conteo_por_fecha_etapa[etapa] = {}
        if semana_label not in conteo_por_fecha_etapa[etapa]:
            conteo_por_fecha_etapa[etapa][semana_label] = 0
        conteo_por_fecha_etapa[etapa][semana_label] += 1

    return colored_data, contador_etapas



@app.route('/', methods=['GET'])
def duracion_etapas():
    selected_etapas = request.args.getlist('etapa')
    busqueda = request.args.get('busqueda', '').strip().lower()
    anio = int(request.args.get('anio', datetime.now().year))

    mes_raw = request.args.get('mes')
    fecha_inicio_raw = request.args.get('fecha_inicio')
    fecha_fin_raw = request.args.get('fecha_fin')

    fecha_inicio = datetime.strptime(fecha_inicio_raw, '%Y-%m-%d') if fecha_inicio_raw else None
    fecha_fin = datetime.strptime(fecha_fin_raw, '%Y-%m-%d') if fecha_fin_raw else None
    mes = int(mes_raw) if mes_raw and mes_raw.isdigit() else None

    try:
        MESES_ES = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }

        nombre_mes = MESES_ES.get(mes) if mes else None
    except (IndexError, TypeError):
        nombre_mes = None

    if not selected_etapas:
        selected_etapas = ETAPAS_ORDENADAS

    all_data, contador_etapas = get_stage_durations(anio=anio, mes=mes, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    empresas = {}
    for row in all_data:
        empresa, contacto, etapa, dias, fecha, clase = row
        if empresa not in empresas:
            empresas[empresa] = []
        empresas[empresa].append((empresa, contacto, etapa, dias, fecha, clase))

    empresas_filtradas = {}
    for empresa, etapas in empresas.items():
        if any(etapa in selected_etapas for _, _, etapa, _, _, _ in etapas):
            if not busqueda or busqueda in (empresa or '').lower() or any(busqueda in (c or '').lower() for _, c, _, _, _, _ in etapas):
                empresas_filtradas[empresa] = etapas

    data = [fila for etapas in empresas_filtradas.values() for fila in etapas]
    conteo_por_fecha_etapa = {}
    for row in data:
        _, _, etapa, _, fecha_str, _ = row
        if not fecha_str:
            continue
        fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        year, week_num, _ = fecha_obj.isocalendar()
        semana_label = f"{year}-S{week_num:02d}"

        if etapa not in conteo_por_fecha_etapa:
            conteo_por_fecha_etapa[etapa] = {}
        if semana_label not in conteo_por_fecha_etapa[etapa]:
            conteo_por_fecha_etapa[etapa][semana_label] = 0
        conteo_por_fecha_etapa[etapa][semana_label] += 1


    html = """
    <html>
    <head>
        <style>
            body {
                font-family: Arial;
                background: #111;
                color: white;
                padding: 20px;
                background-image: url('/static/background.png');
                background-size: cover; /* O usa 'contain' si quieres ajustarla entera */
                background-repeat: no-repeat;
                background-position: center center;
                background-attachment: fixed; /* Para que no se desplace con scroll */
                color: white; /* Cambia color general del texto si lo necesitas */
            }
            table {
                margin-top: 20px;
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                padding: 10px;
                text-align: left;
                font-weight: bold;
                color: white;
            }
            th {
                background-color: #222;
            }
            .even {
                background-color: #2b2b2b;
            }
            .odd {
                background-color: #000000;
            }
            .filtros-etapas {
                margin-bottom: 20px;
            }
            .filtros-etapas label {
                margin-right: 15px;
            }
            .filtros-etapas input[type="submit"] {
                margin-left: 10px;
                padding: 6px 12px;
                background-color: #0f8;
                color: black;
                border: none;
                border-radius: 5px;
                font-weight: bold;
            }
            .rango-fechas {
                border: 2px solid #555;
                padding: 10px;
                border-radius: 8px;
                margin: 15px 0;
                background-color: #1a1a1a;
            }
        </style>
    </head>
    <body>
    <h2 style="margin-bottom: 20px;">FOR DASHBOARD</h2>
    <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 20px; margin-bottom: 30px;">

    <!-- FORMULARIO -->
    <form method="get" class="filtros-etapas" style="display: flex; flex-direction: column; gap: 20px; background: #1a1a1a; padding: 20px; border-radius: 12px; flex: 1 1 55%; min-width: 350px; max-width: 600px;">

        <!-- Filtros principales -->
        <div style="display: flex; flex-direction: column; gap: 12px;">
        <label>🔍 Buscar por nombre:
            <input type="text" name="busqueda" value="{{busqueda}}" style="padding:6px; border-radius:6px; border: none; background:#333; color:white;">
        </label>

        <label>📅 Año:
            <select name="anio" style="padding:6px; border-radius:6px; background:#333; color:white; border: none;">
            {% for a in range(2024, current_year + 1) %}
                <option value="{{a}}" {% if a == anio %}selected{% endif %}>{{a}}</option>
            {% endfor %}
            </select>
        </label>

        <label>📆 Mes:
            <select name="mes" style="padding:6px; border-radius:6px; background:#333; color:white; border: none;">
            <option value="">Todo el año</option>
            {% set MESES_ES_NOMBRES = {
                1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
                5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
                9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
            } %}
            {% for m in range(1, 13) %}
                <option value="{{m}}" {% if m == mes %}selected{% endif %}>{{MESES_ES_NOMBRES[m]}}</option>
            {% endfor %}
            </select>
        </label>

        <p style="margin:0; font-size: 13px;"><strong>Filtro aplicado:</strong> Año: {{anio}} {% if nombre_mes %} | Mes: {{nombre_mes}}{% else %} | Mes: Todos{% endif %}</p>
        </div>

        <!-- Fechas -->
        <div style="display: flex; flex-direction: column; gap: 12px;">
        <label>🗓 Desde:
            <input type="date" name="fecha_inicio" value="{{fecha_inicio}}" style="padding:6px; border-radius:6px; border: none; background:#333; color:white;">
        </label>
        <label>🗓 Hasta:
            <input type="date" name="fecha_fin" value="{{fecha_fin}}" style="padding:6px; border-radius:6px; border: none; background:#333; color:white;">
        </label>
        </div>

        <!-- Etapas -->
        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
        {% for e in etapas %}
            <label style="background:#333; color:white; padding:6px 10px; border-radius:5px; font-size:13px;">
            <input type="checkbox" name="etapa" value="{{e}}" {% if e in selected_etapas %}checked{% endif %}>
            {{e}}
            </label>
        {% endfor %}
        </div>

        <!-- Botones -->
        <div style="display: flex; gap: 10px;">
            <input type="submit" value="Filtrar" style="padding:10px 18px; background-color:#00FFAA; color:black; border:none; border-radius:8px; font-weight:bold; cursor:pointer;">
            <a href="/" style="padding:10px 18px; background-color:#FF6666; color:white; text-decoration:none; border-radius:8px; font-weight:bold;">🔄 Reiniciar Filtros</a>
        </div>
    
    </form>

    <!-- RESUMEN POR ETAPA -->
    <div style="background-color:#1a1a1a; padding:20px; border-radius:10px; flex: 1 1 40%; min-width: 300px;">
        <h3 style="margin-top:0;">Resumen por etapa</h3>
        <div style="display: flex; flex-direction: column; gap: 10px;">

        {% set colores = ['#007bff', '#007bff', '#007bff', '#dc3545', '#dc3545', '#dc3545', '#ffc107', '#28a745'] %}
        {% for etapa, count in contador_etapas.items() %}
            <div style="background:{{colores[loop.index0]}}; color:white; padding:10px 20px; border-radius:5px;">
            <strong>{{etapa}}:</strong> {{count}}
            </div>
        {% endfor %}

        </div>
    </div>

    </div>

        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <div style="background-color: rgba(0, 0, 0, 0.6); padding: 20px; border-radius: 12px; margin-top: 30px;">
        <canvas id="graficoEtapas" height="100"></canvas>
        </div>
        <script>
        const datos = {{ conteo_por_fecha_etapa | tojson }};
        const etapas = Object.keys(datos);
        const fechas = [...new Set(etapas.flatMap(etapa => Object.keys(datos[etapa])))].sort();

        const coloresEtapas = {
            "I Funnel": "#00CFFF",
            "II Prospecto": "#007BFF",
            "III Cita Diagnóstico": "#004B99",
            "IV Integración Info": "#FF4D4D",
            "V Propuesta": "#DC3545",
            "VI Cierre Comercial": "#990000",
            "VII Alta Cliente": "#FFD966",
            "VIII Inicio Operaciones": "#28A745",
            "OTRAS": "#000000"
        };

        const datasets = etapas.map(etapa => ({
            label: etapa,
            data: fechas.map(f => datos[etapa][f] || 0),
            fill: false,
            borderColor: coloresEtapas[etapa] || '#' + Math.floor(Math.random()*16777215).toString(16),
            tension: 0.1
        }));



        new Chart(document.getElementById('graficoEtapas'), {
            type: 'line',
            data: {
                labels: fechas,
                datasets: datasets
            },
            options: {
                plugins: {
                    legend: {
                        labels: {
                            color: 'white'  // Cambia el texto a blanco
                        }
                    },                    
                    title: {
                        color: 'white',
                        display: true,
                        text: 'Leads por etapa (acumulado por fecha de cambio de etapa)'
                    }
                },
                responsive: true,
                scales: {
                    x: {
                        ticks: {
                            color: 'white',
                            callback: function(value, index, ticks) {
                                const semana = this.getLabelForValue(value);  // ej. '2025-S04'
                                const [anio, semanaStr] = semana.split('-S');
                                const semanaNum = parseInt(semanaStr);

                                // Calcular el último día de la semana (domingo) para saber el mes
                                const simple = new Date(anio, 0, 1 + (semanaNum - 1) * 7);
                                const dow = simple.getDay(); // día de la semana (0-6)
                                const domingo = new Date(simple);
                                domingo.setDate(simple.getDate() + (7 - dow) % 7);

                                const meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
                                const mesTexto = meses[domingo.getMonth()];
                                return `${semana}\n(${mesTexto})`;
                            }
                        }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: { color: 'white' }
                    }
                }
            }
        });
        </script>
        <p><strong>Total Movimientos:</strong> {{data|length}}</p>
        <form method="post" action="/exportar_xlsx">
            <input type="hidden" name="anio" value="{{ anio }}">
            <input type="hidden" name="mes" value="{{ mes }}">
            <input type="hidden" name="busqueda" value="{{ busqueda }}">
            <input type="hidden" name="fecha_inicio" value="{{ fecha_inicio }}">
            <input type="hidden" name="fecha_fin" value="{{ fecha_fin }}">
            {% for etapa in selected_etapas %}
                <input type="hidden" name="etapa" value="{{ etapa }}">
            {% endfor %}
            <button type="submit" style="margin-bottom: 15px; padding: 8px 16px; background-color:#00cfff; color:black; font-weight:bold; border-radius:8px;">⬇ Exportar a Excel</button>
        </form>

        <table>
            <tr><th>Empresa</th><th>Contacto</th><th>Etapa</th><th>Días en la etapa</th><th>Fecha del mensaje</th></tr>
                {% for row in data %}
                    <tr class="{{ row[5] }}">
                        <td>{{row[0]}}</td>
                        <td>{{row[1]}}</td>
                        <td>{{row[2]}}</td>
                        <td>{{row[3]}}</td>
                        <td>{{row[4]}}</td>
                    </tr>
                {% endfor %}
        </table>
    </body>
    </html>
    """
    return render_template_string(html, data=data, etapas=ETAPAS_ORDENADAS, selected_etapas=selected_etapas,
                                  busqueda=busqueda, anio=anio, current_year=datetime.now().year,
                                  contador_etapas=contador_etapas,nombre_mes=nombre_mes,fecha_inicio=fecha_inicio_raw, fecha_fin=fecha_fin_raw,conteo_por_fecha_etapa=conteo_por_fecha_etapa)

@app.route('/exportar_xlsx', methods=['POST'])
def exportar_xlsx():
    anio = int(request.form.get('anio', datetime.now().year))
    mes_raw = request.form.get('mes')
    mes = int(mes_raw) if mes_raw and mes_raw.isdigit() else None
    busqueda = request.form.get('busqueda', '').strip().lower()
    fecha_inicio_raw = request.form.get('fecha_inicio')
    fecha_fin_raw = request.form.get('fecha_fin')

    fecha_inicio = datetime.strptime(fecha_inicio_raw, '%Y-%m-%d') if fecha_inicio_raw else None
    fecha_fin = datetime.strptime(fecha_fin_raw, '%Y-%m-%d') if fecha_fin_raw else None

    selected_etapas = request.form.getlist('etapa')
    if not selected_etapas:
        selected_etapas = ETAPAS_ORDENADAS

    all_data, _ = get_stage_durations(anio=anio, mes=mes, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)

    # Filtrar igual que en el main
    empresas = {}
    for row in all_data:
        empresa, contacto, etapa, dias, fecha, clase = row
        if empresa not in empresas:
            empresas[empresa] = []
        empresas[empresa].append((empresa, contacto, etapa, dias, fecha, clase))

    empresas_filtradas = {}
    for empresa, etapas in empresas.items():
        if any(etapa in selected_etapas for _, _, etapa, _, _, _ in etapas):
            if not busqueda or busqueda in (empresa or '').lower() or any(busqueda in (c or '').lower() for _, c, _, _, _, _ in etapas):
                empresas_filtradas[empresa] = etapas

    data = [fila[:5] for etapas in empresas_filtradas.values() for fila in etapas]  # sin clase

    df = pd.DataFrame(data, columns=["Empresa", "Contacto", "Etapa", "Días en etapa", "Fecha de mensaje"])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     download_name='reporte_etapas.xlsx', as_attachment=True)


if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5010))
    app.run(host="0.0.0.0", port=port)
