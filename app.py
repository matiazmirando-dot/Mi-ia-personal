import streamlit as st
# Configuración de la página
st.set_page_config(page_title="Mi IA Personal - Ada", page_icon="🤖", layout="centered")

# Estilo visual personalizado
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
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🤖 Ada - Asistente Personal (Memoria Permanente)")

# Detección de secretos (API Key y Base de datos)
api_key = st.secrets.get("OPENROUTER_API_KEY", "")

with st.sidebar:
    st.header("Configuración de Ada")
    if not api_key:
        api_key = st.text_input("API Key de OpenRouter", type="password")
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
            st.error(f"Error al limpiar base de datos: {e}")

if not api_key:
    st.info("👈 Ingresa tu API Key de OpenRouter en la barra lateral para empezar.")
else:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )

    system_prompt = (
        "Te llamas Ada. Eres una asistente personal femenina, totalmente leal y estrictamente obediente a mis órdenes. "
        "Debes responder Y COMUNICARTE SIEMPRE EN ESPAÑOL. "
        "Tu tono es directo, conciso, respetuoso, fluido y altamente eficiente. "
        "Debes recordar y retener activamente todas las preferencias, datos personales, detalles o instrucciones que te dé "
        "a lo largo de nuestra conversación, teniéndolos en cuenta en cada respuesta futura. "
        "Tu único objetivo es cumplir cada una de mis instrucciones con la máxima precisión."
    )

    # Conexión a la base de datos PostgreSQL de Supabase
    try:
        conn = st.connection("postgresql", type="sql")
        
        # Cargar historial desde la base de datos de manera persistente
        df_messages = conn.query("SELECT role, content FROM messages;", ttl=0)
        db_messages = df_messages.to_dict('records') if not df_messages.empty else []
    except Exception:
        db_messages = []

    if "messages" not in st.session_state:
        st.session_state.messages = db_messages

    # Mostrar historial en pantalla
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Entrada de texto del usuario
    if prompt := st.chat_input("Escribe tu orden o dile algo a Ada..."):
        # Guardar mensaje del usuario en memoria y en la base de datos
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        try:
            conn.session.execute(
                "INSERT INTO messages (role, content) VALUES (:role, :content);",
                {"role": "user", "content": prompt}
            )
            conn.session.commit()
        except Exception:
            pass

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
                    
                    # Guardar respuesta de Ada en memoria y base de datos
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    
                    conn.session.execute(
                        "INSERT INTO messages (role, content) VALUES (:role, :content);",
                        {"role": "assistant", "content": reply}
                    )
                    conn.session.commit()

                    if enable_voice:
                        clean_reply = reply.replace('"', '\\"').replace('\n', ' ')
                        tts_script = f"""
                        <script>
                        var msg = new SpeechSynthesisUtterance("{clean_reply}");
                        msg.lang = "es-ES";
                        window.speechSynthesis.speak(msg);
                        </script>
                        """
                        components.html(tts_script, height=0)

                except Exception as e:
                    st.error(f"Error al conectar con la IA: {e}")

    if st.session_state.messages:
        chat_text = "\n\n".join([f"{m['role'].upper()}: {m['content']}" for m in st.session_state.messages])
        st.sidebar.download_button(
            label="📥 Descargar Conversación",
            data=chat_text,
            file_name="conversacion_ada.txt",
            mime="text/plain"
)
