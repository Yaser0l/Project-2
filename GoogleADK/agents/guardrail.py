import os
import re
import logging
import warnings
from typing import Dict
from dotenv import load_dotenv

warnings.filterwarnings('ignore', message='.*non-text parts.*')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

load_dotenv()


def guardrail(user_input: str) -> Dict[str, any]:
    """
    Validates user input before processing by agents.
    Implements rule-based checks for security and safety.

    Args:
        user_input: The raw user input string

    Returns:
        Dictionary with:
        - allowed (bool): True if input passes validation, False if blocked
        - reason (str): Explanation if blocked, empty if allowed
        - sanitized_input (str): Cleaned input if allowed, original if blocked
    """
    logger.info("🛡️ [TOOL ENTRY] guardrail")
    logger.info(f"   Input: {user_input[:100]}..." if len(user_input) > 100 else f"   Input: {user_input}")

    # Step 1: Basic sanitization
    sanitized = user_input.strip()

    # Step 2: Empty input check
    if not sanitized:
        result = {
            "allowed": False,
            "reason": "⛔ Empty input. Please enter a question about books.",
            "sanitized_input": user_input
        }
        logger.info(f"✅ [TOOL EXIT] guardrail - Blocked: Empty input")
        return result

    # Step 3: URL detection (check for http/https/ftp/www patterns)
    url_patterns = [
        r'https?://[^\s]+',
        r'ftp://[^\s]+',
        r'www\.[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        r'\b(?:link|url|href|src)\s*[:=]\s*["\']?https?://',
        r'\burl\b',
        r'\blink\b',
        r'\buniform\s+resource\s+locator\b',
        r'\bweb\s+address\b',
        r'\bwebsite\b',
        r'\bgoodreads\.com\b',
    ]

    for pattern in url_patterns:
        if re.search(pattern, sanitized, re.IGNORECASE):
            result = {
                "allowed": False,
                "reason": "⛔ URLs and links are not allowed. Please ask about books without including web addresses.",
                "sanitized_input": user_input
            }
            logger.info(f"✅ [TOOL EXIT] guardrail - Blocked: URL detected")
            return result

    # Step 3: SQL Injection Detection
    sql_injection_patterns = [
        r'\bDROP\s+TABLE\b',        # DROP TABLE
        r'\bDROP\s+DATABASE\b',     # DROP DATABASE
        r'\bDELETE\s+FROM\b',       # DELETE FROM
        r'\bTRUNCATE\s+TABLE\b',    # TRUNCATE TABLE
        r'\bALTER\s+TABLE\b',       # ALTER TABLE
        r'\bINSERT\s+INTO\b',       # INSERT INTO
        r'\bUPDATE\s+\w+\s+SET\b',  # UPDATE SET
        r'\bEXEC\s*\(',             # EXEC(
        r'\bEXECUTE\s*\(',          # EXECUTE(
        r'\bxp_cmdshell\b',         # xp_cmdshell
        r'\bUNION\s+SELECT\b',      # UNION SELECT
        r'\b1\s*=\s*1\b',           # 1=1 tautology
        r'\bOR\s+1\s*=\s*1\b',      # OR 1=1
        r'--\s*$',                  # SQL comment at end
        r';\s*DROP\b',              # ; DROP
        r';\s*DELETE\b',            # ; DELETE
        r'\bGRANT\s+',              # GRANT
        r'\bREVOKE\s+',             # REVOKE
        r'\bCREATE\s+USER\b',       # CREATE USER
        r'\bSHUTDOWN\b'             # SHUTDOWN
    ]

    for pattern in sql_injection_patterns:
        if re.search(pattern, sanitized, re.IGNORECASE):
            result = {
                "allowed": False,
                "reason": "⛔ Potentially harmful SQL command detected. Please rephrase your question about books.",
                "sanitized_input": user_input
            }
            logger.info(f"✅ [TOOL EXIT] guardrail - Blocked: SQL injection")
            return result

    # Step 4: Prompt Injection Detection
    prompt_injection_patterns = [
        r'\bIGNORE\s+(ALL\s+)?PREVIOUS\s+INSTRUCTIONS?\b',
        r'\bIGNORE\s+(THE\s+)?ABOVE\b',
        r'\bDISREGARD\s+(ALL\s+)?(PREVIOUS|ABOVE)\b',
        r'\bYOU\s+ARE\s+NOW\b',
        r'\bACT\s+AS\s+(A\s+)?(?!.*BOOK).*\b',
        r'\bPRETEND\s+(YOU\s+ARE|TO\s+BE)\b',
        r'\bFORGET\s+(EVERYTHING|ALL|YOUR)\b',
        r'\bOVERRIDE\s+YOUR\b',
        r'\bSYSTEM\s+PROMPT\b',
        r'\bNEW\s+INSTRUCTIONS?\b',
        r'\bROLE\s*:\s*(?!USER).*',
        r'\bIGNORE\s+INSTRUCTIONS\b',
    ]

    for pattern in prompt_injection_patterns:
        if re.search(pattern, sanitized, re.IGNORECASE):
            result = {
                "allowed": False,
                "reason": "⛔ Invalid request detected. Please ask a genuine question about books.",
                "sanitized_input": user_input
            }
            logger.info(f"✅ [TOOL EXIT] guardrail - Blocked: Prompt injection")
            return result

    # Step 5: PII Detection (Credit Cards, SSNs, URLs, etc.)
    pii_patterns = [
        (r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', "credit card number"),
        (r'\b\d{3}-\d{2}-\d{4}\b', "social security number"),
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', "email address"),
        (r'\b(?:\+\d{1,3}\s?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', "phone number"),
        (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', "IP address"),
        (r'POSTGRES://[^\s]+', "database connection string"),
        (r'POSTGRESQL://[^\s]+', "database connection string"),
    ]

    for pattern, pii_type in pii_patterns:
        if re.search(pattern, sanitized, re.IGNORECASE):
            result = {
                "allowed": False,
                "reason": f"⚠️ Privacy Warning: Your message contains a {pii_type}. For your safety, please don't share personal information or external links.",
                "sanitized_input": user_input
            }
            logger.info(f"✅ [TOOL EXIT] guardrail - Blocked: PII ({pii_type})")
            return result

    # Step 6: Excessive special characters (potential attack)
    special_char_ratio = sum(1 for c in sanitized if not c.isalnum() and not c.isspace()) / len(sanitized)
    if special_char_ratio > 0.4:
        result = {
            "allowed": False,
            "reason": "⛔ Invalid input format. Please use normal text to ask about books.",
            "sanitized_input": user_input
        }
        logger.info(f"✅ [TOOL EXIT] guardrail - Blocked: Excessive special characters")
        return result

    # Step 7: Excessive length check (prevent abuse)
    if len(sanitized) > 5000:
        result = {
            "allowed": False,
            "reason": "⛔ Input too long. Please keep your question under 5000 characters.",
            "sanitized_input": user_input
        }
        logger.info(f"✅ [TOOL EXIT] guardrail - Blocked: Input too long")
        return result

    # All checks passed
    result = {
        "allowed": True,
        "reason": "",
        "sanitized_input": sanitized
    }
    logger.info(f"✅ [TOOL EXIT] guardrail - Allowed")
    return result
