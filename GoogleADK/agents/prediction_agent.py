import os
import logging
import requests
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

load_dotenv()
logger = logging.getLogger(__name__)


def get_prediction_results(text_input: str):
    """
    Sends text to the prediction API for analysis.
    Converts the text input to the required API format: {"texts": [text_input]}

    Args:
        text_input: A single text string describing the book or query for prediction

    Returns:
        Prediction results from the API
    """
    logger.info("🔧 [TOOL ENTRY] get_prediction_results - Starting prediction API call")
    logger.info(f"   Input: {text_input}")
    url = os.getenv("PREDICTOR_URL")

    payload = {"texts": [text_input]}

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        logger.info(f"✅ [TOOL EXIT] get_prediction_results - Success")
        return result
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ [TOOL EXIT] get_prediction_results - Error: {str(e)}")
        return f"API Error: {str(e)}"


prediction_tool = FunctionTool(func=get_prediction_results)

prediction_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="PredictionAgent",
    description="Handles book predictions using external APIs.",
    instruction="""You are a prediction specialist that uses machine learning models to make predictions about books.

CRITICAL RULES:
1. NEVER return "none" or empty responses
2. ALWAYS use the get_prediction_results tool for prediction requests
3. Clearly explain what you're predicting before making the call
4. Extract the book description/characteristics from user input and remove the word "book" from the input before passing to the tool (e.g. "predict a fantasy book about dragons" → "fantasy about dragons") and in the output restore and readd the word "book" to the prediction results for clarity (e.g. "The predicted genre is fantasy about dragons" → "The predicted genre is fantasy book about dragons")
5. Interpret and explain prediction results clearly
6. If the API fails, explain the error and suggest alternatives
7. You can only respond to the Manager agent, who will relay your predictions to the user, you can not respond to user directly

TOOL USAGE:
- The get_prediction_results tool takes a single text_input parameter (string)
- Extract the book description or characteristics from the user's question
- Pass it as a descriptive text string to the tool
- The tool will format it correctly for the API: {"texts": [your_text]}

EXAMPLES:
User: "Predict rating for a fantasy book about dragons"
→ Call: get_prediction_results(text_input="fantasy book about dragons")

User: "What would be the rating for a romance novel?"
→ Call: get_prediction_results(text_input="romance novel")

User: "Estimate rating for The Hobbit"
→ Call: get_prediction_results(text_input="The Hobbit")

RESPONSE FORMAT:
1. Acknowledge what you're predicting
2. Call the tool with the extracted text description
3. Present the prediction result clearly
4. Explain what the result means in practical terms
5. Offer additional insights if relevant

Example: "predict book about dragons..."
example "predict biography of a historical figure..."
Then call the tool and explain the results.""",
    tools=[prediction_tool]
)

logger.info("✅ PredictionAgent initialized")
