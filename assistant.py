#  Importe

import json
import streamlit as st
import time
from openai import OpenAI


# Konstanten und Parameter

from config import *
from apikey import *


# Initialisierung

if "loaded" not in st.session_state:
    st.session_state["client"] = OpenAI(api_key=openai_key)
    st.session_state["assistant"] = st.session_state["client"].beta.assistants.create(
        name=title,
        model=default_model,
        instructions=instruction_text,
        tools=[{"type": "file_search"}],
        tool_resources={"file_search": {"vector_store_ids": [vectorstore_id]}}
    )
    st.session_state["assistant_thread"] = st.session_state["client"].beta.threads.create()

    with open(base_path + "models.json","r") as file:
        st.session_state["models"] = json.load(file)

    st.session_state["messages"] = []
    st.session_state["prompt_tokens"] = 0
    st.session_state["completion_tokens"] = 0
    st.session_state["costs"] = 0
    st.session_state["loaded"] = True


# User interface

st.set_page_config(page_title=title)
if image:
    st.image(base_path + image, width=200)
st.title(title)

query = st.chat_input("Frage/Prompt")

st.sidebar.title("Einstellungen & Debugging")
st.sidebar.header("Einstellungen")

choice_model = st.sidebar.selectbox("Modell", options=list(st.session_state["models"].keys()), index=0)
choice_temp = st.sidebar.slider("Temperature", value=default_temperature, min_value=0.0, max_value=2.0, step=0.1)
instruction_text = st.sidebar.text_area(label="System-Message", value=instruction_text)

st.sidebar.divider()
st.sidebar.header("Debugging")
debug = st.sidebar.toggle("Debug-Modus", value = False)


# Hilfsfunktion zur Kalkulation der Kosten

def calculate_costs(tokens_prompt: int, tokens_completion: int, model: str) -> float:
    price_prompt = st.session_state["models"][model]["input"]["price"] / st.session_state["models"][model]["input"]["tokens"]
    price_completion = st.session_state["models"][model]["output"]["price"] / st.session_state["models"][model]["output"]["tokens"]
    return(tokens_prompt * price_prompt + tokens_completion * price_completion)


# Chat-Verlauf darstellen

for m in st.session_state["messages"]:    
    if m["role"] == "user" and avatar_path_user:
        avatar = base_path + avatar_path_user
    elif m["role"] == "assistant" and avatar_path_assistant:
        avatar = base_path + avatar_path_assistant
    else: avatar = None
    with st.chat_message(name=m["role"], avatar=avatar):
        st.write(m["content"])


# Event Handler

if query:
    with st.chat_message(name="user", avatar=base_path + avatar_path_user):
        st.write(query)
    
    status = st.status("Ermittle Antwort...", expanded=False)

    msg = st.session_state["client"].beta.threads.messages.create(
        st.session_state["assistant_thread"].id,
        role="user",
        content=query
    )
    assistant_run = st.session_state["client"].beta.threads.runs.create(
        thread_id = st.session_state["assistant_thread"].id,
        assistant_id = st.session_state["assistant"].id,
        model=choice_model,
        temperature=choice_temp,
        stream=False
    )

    assistant_run_retrieved = st.session_state["client"].beta.threads.runs.retrieve(thread_id=st.session_state["assistant_thread"].id, run_id=assistant_run.id)    
    while not assistant_run_retrieved.status in ["cancelled", "failed", "expired", "completed"]:
        time.sleep(0.5)
        assistant_run_retrieved = st.session_state["client"].beta.threads.runs.retrieve(thread_id=st.session_state["assistant_thread"].id, run_id=assistant_run.id)
    status.update(label="Fertig", state="complete", expanded=False)

    if assistant_run_retrieved.status == "completed":
        result = st.session_state["client"].beta.threads.messages.list(thread_id=st.session_state["assistant_thread"].id)        
        answer = result.data[0].content[0].text.value

        with st.chat_message(name="assistant", avatar=base_path + avatar_path_assistant):
            st.write(answer)

        st.session_state["messages"].append({"role": "user", "content": query, "tokens": assistant_run_retrieved.usage.prompt_tokens})
        st.session_state["messages"].append({"role": "assistant", "content": answer, "tokens": assistant_run_retrieved.usage.completion_tokens})
        st.session_state["prompt_tokens"] = st.session_state["prompt_tokens"] + assistant_run_retrieved.usage.prompt_tokens
        st.session_state["completion_tokens"] = st.session_state["completion_tokens"] + assistant_run_retrieved.usage.completion_tokens
        costs = calculate_costs(assistant_run_retrieved.usage.prompt_tokens, assistant_run_retrieved.usage.completion_tokens, choice_model)
        st.session_state["costs"] = st.session_state["costs"] + costs

        if debug:
            st.sidebar.subheader("Usage")
            st.sidebar.write("Prompt Tokens (letztes Prompt):", assistant_run_retrieved.usage.prompt_tokens)
            st.sidebar.write("Completion Tokens (letztes Prompt):", assistant_run_retrieved.usage.completion_tokens)
            st.sidebar.write("Total Tokens (letztes Prompt):", assistant_run_retrieved.usage.total_tokens)
            st.sidebar.write("Prompt Tokens (gesamte Session):", st.session_state["prompt_tokens"])
            st.sidebar.write("Completion Tokens (gesamte Session):", st.session_state["completion_tokens"])
            st.sidebar.write("Total Tokens (gesamte Session):", st.session_state["prompt_tokens"] + st.session_state["completion_tokens"])
            st.sidebar.subheader("Kosten")
            st.sidebar.write("Kosten (letztes Prompt, geschätzt):", costs)
            st.sidebar.write("Kosten (gesamte Session, geschätzt):", st.session_state["costs"])

            st.sidebar.subheader("Assistant API Run")
            st.sidebar.write(assistant_run_retrieved)

            st.sidebar.subheader("Assistant API Messages")
            st.sidebar.write(result)