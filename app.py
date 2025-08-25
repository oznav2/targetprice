from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import json

app = FastAPI(title="Target Price Calculator", description="מחשבון מחיר דירה - פרויקט מחיר מטרה")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Pydantic model for request data
class CalculationRequest(BaseModel):
    apartment_area: float
    balcony_area: float
    garden_area: float
    parking_spots: int
    base_price_per_sqm: float
    current_price_per_sqm: float

class PriceCalculator:
    def __init__(self):
        # מקדמי החישוב לפי המסמך
        self.coefficients = {
            'apartment': 1.0,    # שטח דירה - 100%
            'balcony': 0.3,      # מרפסת - 30%
            'garden': 0.4,       # גינה - 40%
            'parking': 2.0       # חניה - 200%
        }
        self.max_difference = 600000  # הפרש מקסימלי
        self.discount_rate = 0.25     # 25% הנחה

    def calculate_weighted_area(self, apartment_area, balcony_area, garden_area, parking_spots):
        """חישוב השטח המשוקלל לפי המקדמים"""
        weighted_area = (
            apartment_area * self.coefficients['apartment'] +
            balcony_area * self.coefficients['balcony'] +
            garden_area * self.coefficients['garden'] +
            parking_spots * self.coefficients['parking']
        )
        return weighted_area

    def calculate_apartment_price(self, apartment_area, balcony_area, garden_area, 
                                parking_spots, base_price_per_sqm, current_price_per_sqm):
        """חישוב מחיר דירה מלא לפי הנוסחה"""
        
        # שטח משוקלל
        weighted_area = self.calculate_weighted_area(
            apartment_area, balcony_area, garden_area, parking_spots
        )
        
        # 1. מחיר בסיסי
        base_total_price = base_price_per_sqm * weighted_area
        
        # 2. מחיר עדכני
        current_total_price = current_price_per_sqm * weighted_area
        
        # 3. מחיר עם 25% הנחה
        discounted_price = base_total_price * (1 - self.discount_rate)
        
        # 4. בדיקת הפרש מקסימלי
        price_difference = current_total_price - discounted_price
        
        # 5. קביעת מחיר סופי
        if price_difference > self.max_difference:
            final_price = current_total_price - self.max_difference
        else:
            final_price = discounted_price
        
        # 6. בדיקה שהמחיר הסופי לא עולה על המחיר הבסיסי
        final_price = min(final_price, base_total_price)
        
        return {
            'weighted_area': round(weighted_area, 2),
            'base_total_price': round(base_total_price),
            'current_total_price': round(current_total_price),
            'discounted_price': round(discounted_price),
            'price_difference': round(price_difference),
            'final_price': round(final_price),
            'savings': round(current_total_price - final_price),
            'max_difference_exceeded': price_difference > self.max_difference
        }

calculator = PriceCalculator()

@app.get("/", response_class=HTMLResponse)
async def index():
    import os
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.post("/calculate")
async def calculate(request: CalculationRequest):
    try:
        # חישוב המחיר
        result = calculator.calculate_apartment_price(
            request.apartment_area, 
            request.balcony_area, 
            request.garden_area, 
            request.parking_spots, 
            request.base_price_per_sqm, 
            request.current_price_per_sqm
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8181, reload=True)