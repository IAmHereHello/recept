from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class Day(str, Enum):
    mon = "mon"
    tue = "tue"
    wed = "wed"
    thu = "thu"
    fri = "fri"
    sat = "sat"
    sun = "sun"


class User(str, Enum):
    michael = "michael"
    rachel = "rachel"


class IngredientIn(BaseModel):
    name: str
    amount: Optional[str] = None
    unit: Optional[str] = None
    sort_order: int = 0


class StepIn(BaseModel):
    sort_order: int
    description: str


class RecipeIn(BaseModel):
    name: str
    description: Optional[str] = None
    cook_time: Optional[int] = None
    difficulty: Optional[Difficulty] = None
    cuisine_type: Optional[str] = None
    is_vegetarian: bool = False
    is_vegan: bool = False
    ingredients: List[IngredientIn] = []
    steps: List[StepIn] = []


class RecipeOut(RecipeIn):
    id: int
    created_at: str
    avg_rating: Optional[float] = None
    last_cooked: Optional[str] = None
    cover_photo: Optional[str] = None


class CookSessionIn(BaseModel):
    recipe_id: int
    cooked_at: Optional[str] = None
    notes: Optional[str] = None
    cooked_by: Optional[User] = None


class CookSessionOut(BaseModel):
    id: int
    recipe_id: int
    cooked_at: str
    notes: Optional[str]
    cooked_by: Optional[User] = None
    ratings: List[dict] = []
    photos: List[str] = []


class PendingReviewOut(BaseModel):
    id: int
    recipe_id: int
    recipe_name: str
    cooked_at: str


class RatingIn(BaseModel):
    user: User
    stars: int = Field(..., ge=1, le=5)


class MealPlanEntry(BaseModel):
    week_start: str
    day: Day
    recipe_id: Optional[int] = None
    locked: bool = False


class ImportUrlRequest(BaseModel):
    url: str


class GroceryRequest(BaseModel):
    week_start: str
