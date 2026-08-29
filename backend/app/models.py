from pydantic import BaseModel, Field, field_validator
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


class StepTrack(str, Enum):
    main = "main"
    meanwhile = "meanwhile"


class StepIn(BaseModel):
    sort_order: int
    description: str
    wait_time_minutes: Optional[int] = None
    track: StepTrack = StepTrack.main


class RecipeIn(BaseModel):
    name: str
    description: Optional[str] = None
    cook_time: Optional[int] = None
    difficulty: Optional[Difficulty] = None
    cuisine_type: Optional[str] = None
    is_vegetarian: bool = False
    is_vegan: bool = False
    is_side_dish: bool = False
    is_baking: bool = False
    portions: Optional[int] = None
    is_freezable: bool = True
    freezer_months: Optional[int] = None
    ingredients: List[IngredientIn] = []
    steps: List[StepIn] = []


class RecipeOut(RecipeIn):
    id: int
    created_at: str
    avg_rating: Optional[float] = None
    last_cooked: Optional[str] = None
    cover_photo: Optional[str] = None
    health_score: Optional[int] = None
    health_grade: Optional[str] = None
    health_rationale: Optional[str] = None
    health_tip: Optional[str] = None
    health_scored_at: Optional[str] = None


class CookSessionIn(BaseModel):
    recipe_id: int
    cooked_at: Optional[str] = None
    notes: Optional[str] = None
    cooked_by: Optional[User] = None
    cooking_mode: bool = False


class PhotoOut(BaseModel):
    id: int
    file_path: str
    uploaded_by: Optional[User] = None


class PendingStepConfirmationOut(BaseModel):
    log_id: int
    track: StepTrack
    sort_order: int
    seconds: int
    avg_seconds: float


class PlanConflictOut(BaseModel):
    week_start: str
    day: str
    existing_recipe_id: int
    existing_recipe_name: Optional[str] = None
    cooked_recipe_id: int
    cooked_recipe_name: Optional[str] = None


class CookSessionOut(BaseModel):
    id: int
    recipe_id: int
    cooked_at: str
    notes: Optional[str]
    cooked_by: Optional[User] = None
    cooking_mode: bool
    current_step: int
    finished_at: Optional[str] = None
    timer_seconds: Optional[int] = None
    timer_started_at: Optional[str] = None
    is_stale: bool = False
    group_id: Optional[int] = None
    pending_step_confirmation: Optional[PendingStepConfirmationOut] = None
    ratings: List[dict] = []
    photos: List[PhotoOut] = []
    # Set only by /finish and /log when the cooked meal's day already held a
    # different, unlocked meal — the client asks the user before overwriting.
    plan_conflict: Optional[PlanConflictOut] = None


class StepAdvanceIn(BaseModel):
    step_index: int


class TimerStartIn(BaseModel):
    seconds: int


class ActiveSessionOut(BaseModel):
    session_id: int
    recipe_id: int
    recipe_name: str
    cooked_by: User
    current_step: int
    total_steps: int
    active_timer_remaining_seconds: Optional[int] = None
    estimated_remaining_seconds: Optional[int] = None
    is_stale: bool = False
    group_id: Optional[int] = None


class SessionGroupCreateIn(BaseModel):
    recipe_ids: List[int] = Field(..., min_length=2, max_length=2)
    cooked_by: Optional[User] = None


class SessionGroupOut(BaseModel):
    group_id: int
    sessions: List[CookSessionOut]


class StepTimeConfirmIn(BaseModel):
    counted: bool


class GroupSessionOut(BaseModel):
    session_id: int
    recipe_id: int
    recipe_name: str
    finished_at: Optional[str] = None


class PendingReviewOut(BaseModel):
    id: int
    recipe_id: int
    recipe_name: str
    cooked_at: str
    is_freezable: bool
    portions: Optional[int] = None


class RatingIn(BaseModel):
    user: User
    stars: float = Field(..., ge=1, le=5)

    @field_validator("stars")
    @classmethod
    def stars_must_be_half_step(cls, v: float) -> float:
        if (v * 2) % 1 != 0:
            raise ValueError("stars must be in increments of 0.5")
        return v


class MealPlanEntry(BaseModel):
    week_start: str
    day: Day
    recipe_id: Optional[int] = None
    locked: bool = False
    freezer_item_id: Optional[int] = None


class SuggestIn(BaseModel):
    # Recipes the user has already seen and rejected this planning round — the
    # "andere suggesties" / per-day 🔄 re-roll passes these so the next pick is
    # genuinely different instead of the same deterministic top scorer.
    exclude_recipe_ids: List[int] = []


class SideDishIn(BaseModel):
    recipe_id: int


class LogMealIn(BaseModel):
    recipe_id: int
    cooked_at: str  # ISO date or datetime — the day the meal was eaten
    cooked_by: Optional[User] = None


class ImportUrlRequest(BaseModel):
    url: str


class GroceryRequest(BaseModel):
    week_start: str


class FreezerItemIn(BaseModel):
    recipe_id: int
    cook_session_id: Optional[int] = None
    portions_total: int = Field(..., gt=0)
    frozen_at: Optional[str] = None
    expires_at: Optional[str] = None
    added_by: Optional[User] = None


class FreezerItemOut(BaseModel):
    id: int
    recipe_id: int
    recipe_name: str
    cook_session_id: Optional[int] = None
    portions_total: int
    portions_remaining: int
    frozen_at: str
    expires_at: str
    added_by: Optional[User] = None
    created_at: str


class FreezerConsumeIn(BaseModel):
    portions: int = Field(..., gt=0)


class FreezerExpiresIn(BaseModel):
    expires_at: str


class DashboardStatusOut(BaseModel):
    cooking_active: bool
    cooking_recipe_id: int = 0
    cooking_recipe_name: str = ""
    # URL path (served by the /uploads static mount, no auth) to the raw image
    # bytes of the recipe being cooked. Only set while cooking_active is true and
    # that recipe actually has a photo; null otherwise.
    cooking_recipe_image_path: Optional[str] = None
    cook_time_remaining_seconds: int = 0
    planned_today_recipe_id: int = 0
    planned_today_recipe_name: str = ""
    updated_at: str
