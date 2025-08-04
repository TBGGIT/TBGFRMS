from flask import Flask, request, render_template_string
import psycopg2
from datetime import datetime
import re
import calendar
import os
from cryptography.fernet import Fernet

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

def get_stage_durations(anio=None, mes=None):
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
    return colored_data, contador_etapas


@app.route('/', methods=['GET'])
@app.route('/', methods=['GET'])
def duracion_etapas():
    selected_etapas = request.args.getlist('etapa')
    busqueda = request.args.get('busqueda', '').strip().lower()
    anio = int(request.args.get('anio', datetime.now().year))

    mes_raw = request.args.get('mes')
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

    all_data, contador_etapas = get_stage_durations(anio=anio, mes=mes)


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

    html = """
    <html>
    <head>
        <style>
            body {
                font-family: Arial;
                background: #111;
                color: white;
                padding: 20px;
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
        </style>
    </head>
    <body>
        <h2>Duración en etapas por empresa</h2>

        <form method="get" class="filtros-etapas">
            <label>
                Buscar por nombre: <input type="text" name="busqueda" value="{{busqueda}}">
            </label>
            <br><br>
            <label>
                Año:
                <select name="anio">
                    {% for a in range(2024, current_year + 1) %}
                        <option value="{{a}}" {% if a == anio %}selected{% endif %}>{{a}}</option>
                    {% endfor %}
                </select>
            </label>
            <label>
                Mes:
                <select name="mes">
                    <option value="">Todo el año</option>
                    {% for m in range(1, 13) %}
                        <option value="{{m}}" {% if m == mes %}selected{% endif %}>{{m}}</option>
                    {% endfor %}
                </select>
            </label>
            {% for e in etapas %}
                <label>
                    <input type="checkbox" name="etapa" value="{{e}}" {% if e in selected_etapas %}checked{% endif %}>
                    {{e}}
                </label>
            {% endfor %}
            <input type="submit" value="Filtrar">
        </form>
        <p><strong>Filtro aplicado:</strong> 
            Año: {{anio}} 
            {% if nombre_mes %} | Mes: {{nombre_mes}} {% else %} | Mes: Todos {% endif %}
        </p>

        <div style="background-color:#1a1a1a; padding:15px; border-radius:10px; margin-bottom:20px;">
            <h3>Resumen por etapa</h3>
            <div style="display: flex; flex-wrap: wrap; gap: 15px;">
                {% for etapa, count in contador_etapas.items() %}
                    <div style="background:#333; padding:10px 20px; border-radius:5px;">
                        <strong>{{etapa}}:</strong> {{count}}
                    </div>
                {% endfor %}
            </div>
        </div>

        <p><strong>Total filas:</strong> {{data|length}}</p>

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
                                  contador_etapas=contador_etapas,nombre_mes=nombre_mes)


if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5010))
    app.run(host="0.0.0.0", port=port)
