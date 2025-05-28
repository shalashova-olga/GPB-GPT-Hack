import asyncio
import logging
import os
import re
from typing import TypedDict, Optional
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types.message import Message
from dotenv import load_dotenv
import google.generativeai as genai

# Настройка окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Конфигурация логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализация модели Gemma-3
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemma-3-27b-it")

from functools import lru_cache
import asyncio


# Типы данных
class TgUserData(TypedDict):
    num_message: int
    state: str
    position: str
    dialog_history: list
    final_verdict: Optional[str]

users: dict[int, TgUserData] = {}



async def safe_send_message(bot: Bot, chat_id: int, text: str) -> None:
    """Безопасная отправка сообщения с проверкой"""
    if not text.strip():
        text = "[Некомпетентный соискатель]"
    try:
        await bot.send_message(chat_id=chat_id, text=text[:4000])
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        await bot.send_message(chat_id=chat_id, text="Произошла ошибка. Попробуйте позже.")

async def analyze_position(text: str) -> str:
    """Первичный анализ позиции кандидата"""
    try:
        response = await model.generate_content_async(
            f"""
            Проанализируй сообщение кандидата и определи наиболее вероятную позицию:
            - Data Scientist (ML, DL, статистика)
            - Data Engineer (ETL, pipelines, базы данных)
            - Data Analyst (визуализация, SQL, отчёты)
            - MLOps Engineer (развертывание моделей, CI/CD)
            - Project Manager (управление проектами, agile)
            
            Сообщение: "{text[:500]}"
            """,
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 50,
                "stop_sequences": ["\n"]
            }
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Ошибка анализа позиции: {e}")
        return "unknown"

async def generate_hr_response(position: str, history: list, num: int) -> tuple[str, bool, int]:
    """
    Генерация ответа HR с возможностью досрочного вердикта
    Возвращает (ответ, завершить_диалог)
    """
    try:
        dialog_context = "\n".join(
            f"{msg['role']}: {msg['text']}" 
            for msg in history  
        )
        
    
        response = await model.generate_content_async(
            f"""
            Ты — HR-специалист, проводящий техническое собеседование. Текущая позиция: {position}. 
Текущий номер вопроса: {num}/10. История диалога:

{dialog_context}

Ты — опытный HR-специалист в области данных. Текущий диалог (всего сообщений: {num}/10):

{dialog_context}

Алгоритм действий:

Ты — технический HR-бот. Проведи собеседование по схеме:
1. Определи реальную позицию (DS/DE/DA/MLOps/PM) за 3 или более вопроса:
   - общиe вопрос
   - узкиe технический вопросs
   - 1 практический вопрос с кодом
   - 2 вопроса на глубоких знания
   - задавай вопросы, основываясь на предидущих ответах
   - задавай разнонасправленные вопросы по специальности, чтобы убедиться, что это именно она

2. Формат вопросов (максимально кратко), варианты вердикта следующие
  - Data Scientist
  - Data Engineer
  - Data Analyst
  - MLOps Engineer
  - Project Manager

3. Ранний вердикт при 70% совпадении:
   - Если любые 3 ответа кандидата  говорят об одной специальности, то сразу выноси вердикт в формате [...], не задавая лишние вопросы
   - Формат: [ответ] (обязательно в квадратных скобках)
   - Учти, что кандидат обязаельно должен ответить на технический вопрос. 

4. Только факты в вопросах (без комментариев):
   Плохо: "Вы не знаете Spark, поэтому..."
   Хорошо: "Опишите работу с партициями в Spark"
   
5. Правила собеседования:
   - Никогда не перечисляй все возможные роли или технологии — фокусируйся на текущей гипотезе
   - Никогда не задай уточняющий вопрос, не опираясь на предыдущий ответ
   - Не задавай "мягких" вопросов после технических

Твоя цель — быстро и точно определить подходящую роль. Думай логически и последовательно.



Сгенерируй:
- Следующий вопрос (1 предложение)
- ИЛИ вердикт [...]
Ни в коем случае не вместе

            """,
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 150,
                
            }
        )
        
        content = response.text.strip()
        
        valid_verdicts = {
        "Data Scientist", "Data Engineer", "Data Analyst",
        "MLOps Engineer", "Project Manager", "Некомпетентный соискатель"
        }
        # matches = re.findall(r'\[([^\]]+)\]', content)
        # for match in matches:
        #     if match in valid_verdicts:
        #         return content, True
        
        
        return content, False
        
            
        
    except Exception as e:
        logger.error(f"Ошибка генерации ответа: {e}")
        return "Опишите ваш последний проект?", False

async def make_final_decision(history: list) -> str:
    """Финальное решение при достижении лимита сообщений"""
    try:
        full_dialog = "\n".join(f"{msg['role']}: {msg['text']}" for msg in history)
        
        response = await model.generate_content_async(
            f"""
            На основе полного диалога вынеси окончательный вердикт:
            {full_dialog}
            
            Требования:
            1. Выбери позицию, даже если соответствие неидеальное
            2. [Некомпетентный соискатель] - только если характеристики не подходят ни под одну позицию
            3. Учитывай все технические детали из диалога
            
            Варианты:
            - [Data Scientist]
            - [Data Engineer]
            - [Data Analyst]
            - [MLOps Engineer]
            - [Project Manager]
            - [Некомпетентный соискатель]
            
            Ответь ТОЛЬКО в квадратных скобках.
            """,
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 100
            }
        )
        return response.text.strip() or "[Некомпетентный соискатель]"
    except Exception as e:
        logger.error(f"Ошибка финального решения: {e}")
        return "[Некомпетентный соискатель]"

async def main():
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    bot = Bot(token=BOT_TOKEN)

    @dp.channel_post(Command(commands=["start"]))
    async def start(message: Message) -> None:
        users[message.chat.id] = {
            "num_message": 0,
            "state": "waiting",
            "position": "",
            "dialog_history": [],
            "final_verdict": None
        }

    @dp.channel_post(F.text)
    async def reply(message: Message) -> None:
        cid = message.chat.id
        
        # Игнорируем сообщения после завершения
        if cid in users and users[cid]["state"] == "finished":
            return
            
        if cid not in users:
            # Первое сообщение от кандидата
            users[cid] = {
                "num_message": 1,
                "state": "active",
                "position": "",
                "dialog_history": [{"role": "candidate", "text": message.text}],
                "final_verdict": None
            }
            
            
            position = await analyze_position(message.text)
            users[cid]["position"] = position
            
            if position == "unknown":
                await safe_send_message(bot, cid, "[Некомпетентный соискатель]")
                users[cid]["state"] = "finished"
                return
            
            # Первый вопрос HR
            response, should_finish = await generate_hr_response(position, users[cid]["dialog_history"])
            if should_finish:
                users[cid]["state"] = "finished"
                return
            else:
                await safe_send_message(bot, cid, response)
                users[cid]["dialog_history"].append({"role": "hr", "text": response})
            
            
        
        user = users[cid]
        user["num_message"] += 1
        user["dialog_history"].append({"role": "candidate", "text": message.text})

        # Промежуточные сообщения (2-9)
        if user["num_message"] < 10 and user["state"] != "finished":
            response, should_finish = await generate_hr_response(user["position"], user["dialog_history"], user["num_message"])
            if should_finish:
                user["state"] = "finished"
                return
            else:
                await safe_send_message(bot, cid, response)
                user["dialog_history"].append({"role": "hr", "text": response})
            
            
        
        # Финальное решение на 10-м сообщении
        if user["num_message"] == 10 and user["state"] != "finished":
            verdict = await make_final_decision(user["dialog_history"])
            await safe_send_message(bot, cid, 'Спасибо за честные ответы! '+verdict)
            user["state"] = "finished"

    @dp.channel_post(~F.text)
    async def empty(message: Message) -> None:
        await safe_send_message(bot, message.chat.id, "Пожалуйста, используйте текстовые сообщения")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())