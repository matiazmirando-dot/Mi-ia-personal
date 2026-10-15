import base64
import sqlite3
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI

# -------------------- Configuración --------------------
st.set_page_config(
    page_title="Ada - Asistente personal",
    page_icon="🤖",
    layout="centered",
)

st.markdown(
    """
    <style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .stChatMessage {
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🤖 Ada — Asistente personal")
st.caption("Chat, memoria elegida por ti y controles para borrar tus datos.")

# SQLite no requiere un servidor ni cuesta dinero. En alojamientos efímeros,
# el archivo puede desaparecer al reiniciar o volver a desplegar la aplicación.
DB_PATH = Path(__file__).with_name("ada.db")


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


def load_messages(conn):
    rows = conn.execute(
        "SELECT role, content FROM messages ORDER BY id ASC"
    ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def load_memories(conn):
    return conn.execute(
        "SELECT id, content, created_at FROM memories ORDER BY id DESC"
    ).fetchall()


def clear_messages(conn):
    conn.execute("DELETE FROM messages")
    conn.commit()


def save_message(conn, role, content):
    conn.execute(
        "INSERT INTO messages (role, content) VALUES (?, ?)",
        (role, content),
    )
    conn.commit()


conn = get_db()

# -------------------- Barra lateral --------------------
with st.sidebar:
    st.header("Configuración de Ada")

    try:
        configured_key = st.secrets.get("OPENROUTER_API_KEY", "")
    except Exception:
        configured_key = ""

    api_key = configured_key or st.text_input(
        "Clave API de OpenRouter", type="password",
        help="La clave escrita aquí solo permanece en esta sesión. No la compartas.",
    )

    model_choice = st.selectbox(
        "Modelo",
        [
            "qwen/qwen-2.5-7b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "meta-llama/llama-3-8b-instruct:free",
        ],
    )
    enable_voice = st.checkbox("Leer respuestas en voz alta", value=False)
    temperature = st.slider(
        "Creatividad", min_value=0.0, max_value=1.0, value=0.3, step=0.1
    )

    st.divider()
    if st.button("Borrar todo el historial", use_container_width=True):
        clear_messages(conn)
        st.success("Historial borrado.")
        st.rerun()

# -------------------- Memoria manual --------------------
with st.expander("🧠 Memoria de Ada: guardar o eliminar datos", expanded=True):
    st.write(
        "Solo se usarán como memoria los datos que guardes aquí. "
        "No guardes contraseñas, claves API, datos bancarios ni información "
        "que no quieras enviar al proveedor del modelo."
    )
    with st.form("add_memory_form", clear_on_submit=True):
        new_memory = st.text_area(
            "Dato que quieres que Ada recuerde",
            placeholder="Ej.: Estoy desarrollando una aplicación de tareas en Python.",
            max_chars=2000,
        )
        submitted = st.form_submit_button("Guardar memoria")
        if submitted:
            cleaned = new_memory.strip()
            if cleaned:
                conn.execute(
                    "INSERT INTO memories (content) VALUES (?)", (cleaned,)
                )
                conn.commit()
                st.success("Memoria guardada.")
                st.rerun()
            else:
                st.warning("Escribe un dato antes de guardarlo.")

    memories = load_memories(conn)
    if not memories:
        st.caption("Todavía no hay recuerdos guardados.")
    for memory in memories:
        left, right = st.columns([5, 1])
        with left:
            st.markdown(f"**Memoria {memory['id']}**")
            st.write(memory["content"])
        with right:
            if st.button("Eliminar", key=f"delete_memory_{memory['id']}"):
                conn.execute("DELETE FROM memories WHERE id = ?", (memory["id"],))
                conn.commit()
                st.rerun()

# -------------------- Personalidad y contexto --------------------
system_prompt = """
Te llamas Ada. Eres una asistente personal amigable, muy inteligente,
práctica y cuidadosa. Responde siempre en español salvo que te pidan otro idioma.
Sé clara, honesta y respetuosa. Si no sabes algo, dilo y no inventes datos.
Ayuda con proyectos y explica los pasos de forma concreta.
La memoria que aparece a continuación fue guardada manualmente por la persona.
Úsala solo como contexto relevante; no supongas que recuerdas información que no aparece aquí.
"""

memory_rows = load_memories(conn)
if memory_rows:
    memory_context = "\n".join(f"- {row['content']}" for row in memory_rows)
    system_prompt += "\n\nMEMORIA GUARDADA POR EL USUARIO:\n" + memory_context

# -------------------- Conversación --------------------
messages = load_messages(conn)
for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Escribe un mensaje para Ada...")
if prompt:
    save_message(conn, "user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Ada está pensando..."):
            try:
                if not api_key:
                    st.error(
                        "Añade tu clave de OpenRouter en la barra lateral "
                        "o configura OPENROUTER_API_KEY en Secrets."
                    )
                else:
                    client = OpenAI(
                        base_url="https://openrouter.ai/api/v1",
                        api_key=api_key,
                    )
                    # Volvemos a cargar el historial después de guardar el mensaje
                    # actual; así la pregunta más reciente sí llega al modelo.
                    history = load_messages(conn)[-20:]
                    response = client.chat.completions.create(
                        model=model_choice,
                        temperature=temperature,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            *history,
                        ],
                    )
                    reply = response.choices[0].message.content
                    if not reply or not reply.strip():
                        st.warning("Ada devolvió una respuesta vacía. Inténtalo otra vez.")
                    else:
                        reply = reply.strip()
                        st.markdown(reply)
                        save_message(conn, "assistant", reply)

                        if enable_voice:
                            encoded = base64.b64encode(
                                reply.encode("utf-8")
                            ).decode("ascii")
                            # Base64 evita insertar texto arbitrario directamente
                            # en el código JavaScript.
                            tts_script = f"""
                            <script>
                            try {{
                                const bytesText = atob("{encoded}");
                                const bytes = Uint8Array.from(bytesText, c => c.charCodeAt(0));
                                const text = new TextDecoder("utf-8").decode(bytes);
                                const utterance = new SpeechSynthesisUtterance(text);
                                utterance.lang = "es-ES";
                                window.speechSynthesis.cancel();
                                window.speechSynthesis.speak(utterance);
                            }} catch (error) {{ console.error(error); }}
                            </script>
                            """
                            components.html(tts_script, height=0)
            except Exception as error:
                st.error(
                    "No se pudo conectar con OpenRouter. Comprueba la conexión, "
                    "la clave y que el modelo gratuito siga disponible. "
                    f"Detalle técnico: {error}"
                )

# -------------------- Exportar historial --------------------
with st.sidebar:
    current_messages = load_messages(conn)
    if current_messages:
        export_text = "\n\n".join(
            f"{item['role'].upper()}: {item['content']}"
            for item in current_messages
        )
        st.download_button(
            "📥 Descargar conversación",
            data=export_text,
            file_name="conversacion_ada.txt",
            mime="text/plain",
            use_container_width=True,
        )

conn.close()
