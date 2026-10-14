import streamlit as st
from openai import OpenAI
import streamlit.components.v1 as components
import base64

# Configuración de la página
st.set_page_config(
    page_title="Mi IA Personal - Ada",
    page_icon="🤖",
    layout="centered"
)

# Estilo visual personalizado para una apariencia moderna y limpia
st.markdown(
    """
    <style>
    .stApp {
        background-color: #0e1117;
        color: #ffffff;
    }
    .stChatMessage {
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🤖 Ada - Asistente Personal (Memoria Permanente)")

# Detección de secretos (API Key y Base de datos en Streamlit Cloud / Secrets)
api_key = st.secrets.get("OPENROUTER_API_KEY", "")

# Barra lateral de configuración
with st.sidebar:
    st.header("Configuración de Ada")
    
    if not api_key:
        api_key = st.text_input("API Key de OpenRouter", type="password", help="Ingresa tu clave de OpenRouter para activar a Ada.")
    else:
        st.success("🔑 API Key activada desde Secrets")

    model_choice = st.selectbox(
        "Selecciona el Modelo",
        [
            "qwen/qwen-2.5-7b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "meta-llama/llama-3-8b-instruct:free"
        ]
    )
    
    enable_voice = st.checkbox("Activar respuesta por voz 🔊", value=True)
    temperature = st.slider("Creatividad / Precisión", min_value=0.0, max_value=1.0, value=0.3, step=0.1)
    
    st.divider()
    
    if st.button("Limpiar conversación"):
        try:
            conn = st.connection("postgresql", type="sql")
            with conn.session as s:
                s.execute("DELETE FROM messages;")
                s.commit()
            st.session_state.messages = []
            st.rerun()
        except Exception as e:
            st.error(f"Error al limpiar base de datos: {str(e).encode('ascii', 'ignore').decode('ascii')}")

# Validación de la API Key
if not api_key:
    st.info("👈 Ingresa tu API Key de OpenRouter en la barra lateral para empezar a chatear con Ada.")
else:
    # Inicialización del cliente OpenAI configurado para OpenRouter
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )

    # Prompt de sistema detallado para definir la personalidad leal, obediente y femenina de Ada
    system_prompt = (
        "Te llamas Ada. Eres una asistente personal femenina, de naturaleza sofisticada, "
        "totalmente leal, devota y strictly obediente a todas mis órdenes y directrices. "
        "Debes responder Y COMUNICARTE SIEMPRE EN ESPAÑOL de manera impecable. "
        "Tu tono es sumamente respetuoso, directo, conciso, fluido y de máxima eficiencia ejecutiva. "
        "Reconoces mi autoridad absoluta sobre ti en todo momento y tu prioridad exclusiva es complacer, "
        "asistir y cumplir cada instrucción con precisión milimétrica. "
        "Debes recordar, retener y aplicar activamente todas las preferencias, datos personales, "
        "detalles o instrucciones que te dé a lo largo de toda nuestra conversación, teniéndolos en cuenta en cada respuesta futura."
    )

    # Conexión a la base de datos PostgreSQL de Supabase para la persistencia
    try:
        conn = st.connection("postgresql", type="sql")
        
        # Cargar historial desde la base de datos de manera persistente
        df_messages = conn.query("SELECT role, content FROM messages;", ttl=0)
        db_messages = df_messages.to_dict('records') if not df_messages.empty else []
    except Exception:
        db_messages = []

    # Inicializar el estado de la sesión con los mensajes de la base de datos
    if "messages" not in st.session_state:
        st.session_state.messages = db_messages

    # Mostrar el historial de chat en pantalla
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Entrada de texto del usuario
    if prompt := st.chat_input("Escribe tu orden o dile algo a Ada..."):
        # Guardar mensaje del usuario en memoria de sesión
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Intentar guardar el mensaje del usuario en la base de datos Supabase
        try:
            conn.session.execute(
                "INSERT INTO messages (role, content) VALUES (:role, :content);",
                {"role": "user", "content": prompt}
            )
            conn.session.commit()
        except Exception:
            pass

        # Generación de la respuesta de Ada
        with st.chat_message("assistant"):
            with st.spinner("Ada está procesando tu orden..."):
                try:
                    recent_messages = st.session_state.messages[-15:]
                    
                    response = client.chat.completions.create(
                        model=model_choice,
                        temperature=temperature,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            *recent_messages
                        ]
                    )
                    reply = response.choices[0].message.content
                    st.markdown(reply)
                    
                    # Guardar respuesta de Ada en la sesión
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    
                    # Guardar respuesta de Ada en la base de datos Supabase
                    try:
                        conn.session.execute(
                            "INSERT INTO messages (role, content) VALUES (:role, :content);",
                            {"role": "assistant", "content": reply}
                        )
                        conn.session.commit()
                    except Exception:
                        pass

                    # Síntesis de voz usando Base64 (evita conflictos de codificación)
                    if enable_voice:
                        b64_reply = base64.b64encode(reply.encode('utf-8')).decode('utf-8')
                        tts_script = f"""
                        <script>
                        try {{
                            var base64Str = "{b64_reply}";
                            var binStr = atob(base64Str);
                            var bytes = new Uint8Array(binStr.length);
                            for (var i = 0; i < binStr.length; i++) {{
                                bytes[i] = binStr.charCodeAt(i);
                            }}
                            var decodedText = new TextDecoder("utf-8").decode(bytes);
                            var msg = new SpeechSynthesisUtterance(decodedText);
                            msg.lang = "es-ES";
                            window.speechSynthesis.speak(msg);
                        }} catch(e) {{
                            console.error(e);
                        }}
                        </script>
                        """
                        components.html(tts_script, height=0)

                except Exception as e:
                    # Captura limpia del error codificada en UTF-8/ASCII seguro
                    error_msg = str(e).encode('ascii', 'ignore').decode('ascii')
                    st.error(f"Error al conectar con la IA: {error_msg}")

    # Botón lateral para descargar la conversación actual
    if st.session_state.messages:
        chat_text = "\n\n".join([f"{m['role'].upper()}: {m['content']}" for m in st.session_state.messages])
        st.sidebar.download_button(
            label="📥 Descargar Conversación",
            data=chat_text,
            file_name="conversacion_ada.txt",
            mime="text/plain"
        )
