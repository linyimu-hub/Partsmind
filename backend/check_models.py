import openai,os 
from dotenv import load_dotenv 
load_dotenv() 
c=openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'),base_url=os.getenv('OPENAI_BASE_URL')) 
[print(m.id) for m in c.models.list().data if 'embed' in m.id.lower()] 
