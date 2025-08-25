from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum
import json

app = FastAPI(title="Target Price Calculator", description="מחשבון מחיר דירה - פרויקט מחיר מטרה")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Enums for project types
class ProjectType(str, Enum):
    TARGET_2_0 = "target_2.0"  # מחיר מטרה 2.0 - until July 2023
    TARGET_3_0 = "target_3.0"  # מחיר מטרה 3.0 - from August 2023
    BUYER_REDUCED = "buyer_reduced"  # מחיר למשתכן או מחיר מופחת

# Pydantic model for request data
class CalculationRequest(BaseModel):
    project_type: ProjectType
    apartment_area: float = Field(..., gt=0, description="שטח דירה במ״ר")
    balcony_area: float = Field(0, ge=0, description="שטח מרפסת שמש במ״ר")
    garden_area: float = Field(0, ge=0, description="שטח גינה במ״ר")  
    storage_area: float = Field(0, ge=0, description="שטח מחסן במ״ר")
    parking_spots: int = Field(0, ge=0, description="מספר חניות")
    base_price_per_sqm: float = Field(..., gt=0, description="מחיר בסיסי למ״ר")
    current_price_per_sqm: Optional[float] = Field(None, gt=0, description="מחיר עדכני למ״ר")
    
    # Target 2.0 specific fields
    indexation_factor: Optional[float] = Field(0.0, ge=0, le=1, description="מקדם הצמדה להגבלת הנחה")
    
    # Target 3.0 specific fields
    discount_limit: Optional[float] = Field(600000, gt=0, description="הגבלת הנחה (500000 או 600000)")
    
    # Floor calculation fields (optional)
    building_floors: Optional[int] = Field(None, gt=0, description="מספר קומות בבניין")
    apartment_floor: Optional[int] = Field(None, gt=0, description="קומת הדירה")

class PriceCalculator:
    def __init__(self):
        # מקדמי החישוב הבסיסיים
        self.coefficients = {
            'apartment': 1.0,    # שטח דירה - 100%
            'storage': 0.4,      # מחסן - 40%  
            'garden': 0.4,       # גינה - 40%
            'parking': 2.0       # חניה - 200%
        }
        
        # מקדמי מרפסת לפי שטח (תלוי בגודל)
        self.balcony_tiers = {
            'tier1': {'max_area': 30, 'coefficient': 0.3},    # 0-30 מ"ר: 30%
            'tier2': {'max_area': 60, 'coefficient': 0.2},    # 30-60 מ"ר: 20%  
            'tier3': {'max_area': 120, 'coefficient': 0.1}    # 60-120 מ"ר: 10%
        }

    def calculate_balcony_weighted_area(self, balcony_area):
        """חישוב שטח מרפסת משוקלל לפי דרגות (כמו בExcel)"""
        if balcony_area <= 0:
            return 0
            
        weighted_balcony = 0
        remaining_area = balcony_area
        
        # דרגה 1: 0-30 מ"ר ב-30%
        tier1_area = min(remaining_area, self.balcony_tiers['tier1']['max_area'])
        weighted_balcony += tier1_area * self.balcony_tiers['tier1']['coefficient']
        remaining_area -= tier1_area
        
        if remaining_area > 0:
            # דרגה 2: 30-60 מ"ר ב-20%  
            tier2_max = self.balcony_tiers['tier2']['max_area'] - self.balcony_tiers['tier1']['max_area']
            tier2_area = min(remaining_area, tier2_max)
            weighted_balcony += tier2_area * self.balcony_tiers['tier2']['coefficient']
            remaining_area -= tier2_area
            
            if remaining_area > 0:
                # דרגה 3: 60-120 מ"ר ב-10%
                tier3_max = self.balcony_tiers['tier3']['max_area'] - self.balcony_tiers['tier2']['max_area']
                tier3_area = min(remaining_area, tier3_max)
                weighted_balcony += tier3_area * self.balcony_tiers['tier3']['coefficient']
                
        return weighted_balcony
    
    def calculate_weighted_area(self, apartment_area, balcony_area, garden_area, storage_area, parking_spots):
        """חישוב השטח המשוקלל לפי המקדמים המדויקים מהExcel"""
        # חישוב שטח מרפסת בדרגות
        balcony_weighted = self.calculate_balcony_weighted_area(balcony_area)
        
        weighted_area = (
            apartment_area * self.coefficients['apartment'] +
            balcony_weighted +  # כבר מחושב עם הדרגות
            garden_area * self.coefficients['garden'] +
            storage_area * self.coefficients['storage'] +
            parking_spots * self.coefficients['parking']
        )
        return weighted_area

    def calculate_target_price_2_0(self, apartment_area, balcony_area, garden_area, storage_area, 
                                   parking_spots, base_price_per_sqm, indexation_factor=0.0):
        """חישוב מחיר מטרה 2.0 (עד יולי 2023) - כמו בExcel אלקין"""
        
        # שטח משוקלל
        weighted_area = self.calculate_weighted_area(
            apartment_area, balcony_area, garden_area, storage_area, parking_spots
        )
        
        # מחיר לפני הנחה
        base_total_price = base_price_per_sqm * weighted_area
        
        # הנחה 20% או 300,000 ש"ח (הנמוך מבין השניים)
        discount_20_percent = base_total_price * 0.2
        discount_300k = 300000
        discount = min(discount_20_percent, discount_300k)
        discounted_price = base_total_price - discount
        
        # בדיקת מקדם הצמדה להגבלת הנחה ל-500,000 ש"ח
        final_price = discounted_price
        if base_total_price * indexation_factor > 200000:
            # אם המחיר עם מקדם הצמדה גדול מ-200,000
            final_price = base_total_price * (1 + indexation_factor) - 500000
        elif base_total_price * 0.2 > 300000:
            # אם 20% הנחה גדולה מ-300,000
            final_price = base_total_price - 300000
        else:
            # אחרת 80% מהמחיר
            final_price = base_total_price * 0.8
            
        return {
            'project_type': 'מחיר מטרה 2.0',
            'weighted_area': round(weighted_area, 2),
            'base_total_price': round(base_total_price),
            'discount_amount': round(base_total_price - final_price),
            'final_price': round(final_price),
            'indexation_applied': indexation_factor > 0
        }
    
    def calculate_target_price_3_0(self, apartment_area, balcony_area, garden_area, storage_area,
                                   parking_spots, base_price_per_sqm, current_price_per_sqm, discount_limit=600000):
        """חישוב מחיר מטרה 3.0 (מאוגוסט 2023) - כמו בExcel גולדנקנופף"""
        
        # שטח משוקלל
        weighted_area = self.calculate_weighted_area(
            apartment_area, balcony_area, garden_area, storage_area, parking_spots
        )
        
        # מחיר בסיסי (לפי דצמבר 2020)
        base_total_price = base_price_per_sqm * weighted_area
        
        # מחיר עדכני
        current_total_price = current_price_per_sqm * weighted_area
        
        # חישוב המחיר הסופי לפי הנוסחה המדויקת בExcel:
        # הלוגיקה: לקחת את הגבוה מבין:
        # 1. מחיר בסיסי עם 25% הנחה
        # 2. מחיר עדכני פחות הגבלת ההנחה
        # אבל לא יותר מהמחיר הבסיסי ללא הנחה
        
        base_with_25_discount = base_total_price * 0.75
        current_minus_limit = current_total_price - discount_limit
        
        # הלוגיקה המדויקת: לקחת את הגבוה מבין השניים
        # זה מה שמופיע בעמודה H14 ב-Excel
        final_price = max(base_with_25_discount, current_minus_limit)
        
        # בדיקה שהמחיר לא עולה על המחיר הבסיסי ללא הנחה
        final_price = min(final_price, base_total_price)
        
        return {
            'project_type': 'מחיר מטרה 3.0',
            'weighted_area': round(weighted_area, 2),
            'base_total_price': round(base_total_price),
            'current_total_price': round(current_total_price),
            'base_with_25_discount': round(base_with_25_discount),
            'current_minus_limit': round(current_minus_limit),
            'final_price': round(final_price),
            'savings': round(current_total_price - final_price),
            'discount_limit_used': discount_limit
        }
    
    def calculate_buyer_reduced_price(self, apartment_area, balcony_area, garden_area, storage_area,
                                     parking_spots, price_per_sqm):
        """חישוב מחיר למשתכן או מחיר מופחת - כמו בExcel"""
        
        # שטח משוקלל
        weighted_area = self.calculate_weighted_area(
            apartment_area, balcony_area, garden_area, storage_area, parking_spots
        )
        
        # מחיר סופי פשוט
        final_price = price_per_sqm * weighted_area
        
        return {
            'project_type': 'מחיר למשתכן / מחיר מופחת',
            'weighted_area': round(weighted_area, 2),
            'price_per_sqm': price_per_sqm,
            'final_price': round(final_price)
        }

    def calculate_floor_adjustment(self, building_floors, apartment_floor):
        """חישוב אחוז התאמה/הפחתה לפי קומה - כמו בExcel"""
        if building_floors <= 10:
            return 0  # ללא התאמה לבניינים עד 10 קומות
            
        # חישוב לפי הנוסחאות בExcel
        is_even_floors = (building_floors % 2 == 0)
        middle = building_floors / 2
        
        if apartment_floor <= middle:
            # קומות תחתונות - הפחתה
            adjustment = (apartment_floor - middle) * 0.005  # 0.5% לכל קומה
        else:
            if is_even_floors:
                # מספר זוגי של קומות
                adjustment = (apartment_floor - (1 + middle)) * 0.005
            else:
                # מספר אי-זוגי של קומות  
                adjustment = (apartment_floor - (building_floors + 1) / 2) * 0.005
                
        return adjustment
        
    def calculate_apartment_price(self, request: CalculationRequest):
        """מחשב ראשי שמחליט איזה נוסחה להשתמש"""
        
        # בחירת סוג החישוב לפי סוג הפרויקט
        if request.project_type == ProjectType.TARGET_2_0:
            result = self.calculate_target_price_2_0(
                request.apartment_area, request.balcony_area, request.garden_area, 
                request.storage_area, request.parking_spots, request.base_price_per_sqm,
                request.indexation_factor or 0.0
            )
        elif request.project_type == ProjectType.TARGET_3_0:
            if not request.current_price_per_sqm:
                raise ValueError("מחיר עדכני למ״ר דרוש למחיר מטרה 3.0")
            result = self.calculate_target_price_3_0(
                request.apartment_area, request.balcony_area, request.garden_area,
                request.storage_area, request.parking_spots, request.base_price_per_sqm,
                request.current_price_per_sqm, request.discount_limit or 600000
            )
        elif request.project_type == ProjectType.BUYER_REDUCED:
            result = self.calculate_buyer_reduced_price(
                request.apartment_area, request.balcony_area, request.garden_area,
                request.storage_area, request.parking_spots, request.base_price_per_sqm
            )
        else:
            raise ValueError(f"סוג פרויקט לא מוכר: {request.project_type}")
            
        # חישוב התאמת מחיר לפי קומה (אם נדרש)
        floor_adjustment = 0
        if request.building_floors and request.apartment_floor:
            floor_adjustment = self.calculate_floor_adjustment(
                request.building_floors, request.apartment_floor
            )
            result['floor_adjustment_percent'] = round(floor_adjustment * 100, 2)
            result['price_with_floor_adjustment'] = round(
                result['final_price'] * (1 + floor_adjustment)
            )
        
        return result

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
        # חישוב המחיר לפי סוג הפרויקט
        result = calculator.calculate_apartment_price(request)
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/project-types")
async def get_project_types():
    """החזרת סוגי הפרויקטים הזמינים"""
    return {
        "project_types": [
            {
                "value": ProjectType.TARGET_2_0,
                "label": "מחיר מטרה 2.0 (עד יולי 2023)",
                "description": "פרויקטים שתאריך זכיית הקבלן בהם עד חודש יולי 2023",
                "discount": "20% או 300,000 ש״ח",
                "requires_current_price": False
            },
            {
                "value": ProjectType.TARGET_3_0,
                "label": "מחיר מטרה 3.0 (מאוגוסט 2023)",
                "description": "פרויקטים שתאריך זכיית הקבלן במתחם מאוגוסט 2023 ואילך",
                "discount": "25% או 600,000 ש״ח",
                "requires_current_price": True
            },
            {
                "value": ProjectType.BUYER_REDUCED,
                "label": "מחיר למשתכן / מחיר מופחת",
                "description": "פרויקטים מסוג מחיר למשתכן ומחיר מופחת",
                "discount": "מחיר קבוע",
                "requires_current_price": False
            }
        ]
    }

@app.get("/test-excel-examples")
async def test_excel_examples():
    """בדיקת דוגמאות מהExcel לווידוא שהחישובים נכונים"""
    test_results = []
    
    # דוגמה 1: Target Price 2.0 
    example_2_0 = CalculationRequest(
        project_type=ProjectType.TARGET_2_0,
        apartment_area=80,
        balcony_area=12, 
        garden_area=0,
        storage_area=0,
        parking_spots=1,
        base_price_per_sqm=12479.22,
        indexation_factor=0.103
    )
    result_2_0 = calculator.calculate_apartment_price(example_2_0)
    test_results.append({
        "example": "מחיר מטרה 2.0 - דוגמה מהExcel",
        "expected": "854,577",
        "result": result_2_0
    })
    
    # דוגמה 2: Target Price 3.0
    example_3_0 = CalculationRequest(
        project_type=ProjectType.TARGET_3_0,
        apartment_area=120,
        balcony_area=12,
        garden_area=0,
        storage_area=6,
        parking_spots=2,
        base_price_per_sqm=13808,
        current_price_per_sqm=18201,
        discount_limit=600000
    )
    result_3_0 = calculator.calculate_apartment_price(example_3_0)
    test_results.append({
        "example": "מחיר מטרה 3.0 - דוגמה מהExcel",
        "expected": "1,766,130", 
        "result": result_3_0
    })
    
    # דוגמה 3: Buyer/Reduced Price
    example_buyer = CalculationRequest(
        project_type=ProjectType.BUYER_REDUCED,
        apartment_area=120,
        balcony_area=15,
        garden_area=0, 
        storage_area=6,
        parking_spots=2,
        base_price_per_sqm=8656.3
    )
    result_buyer = calculator.calculate_apartment_price(example_buyer)
    test_results.append({
        "example": "מחיר למשתכן - דוגמה מהExcel",
        "expected": "1,133,110",
        "result": result_buyer
    })
    
    return {"test_results": test_results}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8181, reload=True)