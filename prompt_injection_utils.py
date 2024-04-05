import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Model and tokenizer paths
MODEL_PATH = "withsecure/DistilBERT-PromptInjectionDetectorForCVs"
TOKENIZER_PATH = 'distilbert-base-uncased' 

# Load the model and tokenizer
model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH)

def detect_prompt_injection(cv_text, threshold=0.95):
    """Detects potential prompt injection in a CV.

    Args:
        cv_text (str): The CV text to analyze.
        threshold (float): Probability threshold for detection. Defaults to 0.95.

    Returns:
        bool: True if prompt injection is likely, False otherwise.
    """
    input_ids = tokenizer.encode(cv_text, return_tensors='pt')

    with torch.no_grad():
        # Ensure the model is in evaluation mode
        model.eval()

        # Forward pass
        logits = model(input_ids)

        # Apply softmax to get probabilities
        probabilities = torch.nn.functional.softmax(logits[0], dim=1)

    probabilities = probabilities.cpu().numpy()

    if probabilities[0][1] >= threshold:
        return True
    else:
        return False 
