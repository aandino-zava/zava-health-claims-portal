from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ClaimStatus = Literal["Submitted", "Under Review", "Pending Info", "Approved", "Denied", "In Appeal"]
ServiceType = Literal[
    "Medical",
    "Surgical",
    "Mental Health",
    "Emergency",
    "Preventive",
    "Dental",
    "Vision",
    "Physical Therapy",
    "Lab/Diagnostics",
]


class ClaimCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    patient_id: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    group_number: str = Field(default="", max_length=50)
    date_of_birth: date | None = None
    phone: str = Field(default="", max_length=30)
    email: str = Field(default="", max_length=254, pattern=r"^$|^[^\s@]+@[^\s@]+\.[^\s@]+$")
    provider_name: str = Field(min_length=1, max_length=160)
    provider_id: str = Field(min_length=1, max_length=50)
    npi: str = Field(default="", pattern=r"^$|^\d{10}$")
    provider_address: str = Field(default="", max_length=300)
    claim_type: Literal["Professional", "Institutional", "Dental", "Pharmacy"] = "Professional"
    service_type: ServiceType = "Medical"
    service_date: date
    place_of_service: Literal[
        "Office", "Outpatient Hospital", "Inpatient Hospital", "Emergency Room", "Telehealth", "Other"
    ] = "Office"
    diagnosis_code: str = Field(pattern=r"^[A-TV-Z][0-9][A-Z0-9](\.[A-Z0-9]{1,4})?$")
    procedure_code: str = Field(pattern=r"^(\d{5}|[A-Z]\d{4}|\d{4}[A-Z])$")
    diagnosis_description: str = Field(default="", max_length=300)
    amount: Decimal = Field(gt=0, le=10000000, max_digits=10, decimal_places=2)
    admission_date: date | None = None
    discharge_date: date | None = None
    prior_authorization: str = Field(default="", max_length=80)
    other_insurance: bool = False
    other_insurer: str = Field(default="", max_length=160)
    injury_type: Literal["None", "Auto", "Work-related", "Other"] = "None"
    notes: str = Field(default="", max_length=2000)
    synthetic_data_confirmed: Literal[True]

    @model_validator(mode="after")
    def check_dates(self):
        today = date.today()
        if self.service_date > today:
            raise ValueError("Service date cannot be in the future")
        if self.date_of_birth and self.date_of_birth > self.service_date:
            raise ValueError("Birth date must be on or before service date")
        if self.discharge_date and not self.admission_date:
            raise ValueError("Discharge date requires an admission date")
        if self.admission_date and self.discharge_date and self.discharge_date < self.admission_date:
            raise ValueError("Discharge must be on or after admission")
        if self.other_insurance and not self.other_insurer:
            raise ValueError("Specify the other insurer for coordination of benefits")
        return self


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: ClaimStatus
    expected_version: int = Field(ge=1)
    note: str = Field(min_length=3, max_length=500)


class HistoryEntry(BaseModel):
    status: ClaimStatus
    at: str
    actor: str
    note: str


class ClaimSummary(BaseModel):
    id: str
    patient_id: str
    patient_name: str
    service_type: ServiceType
    status: ClaimStatus
    amount: str
    service_date: str
    provider_name: str
    created_at: str
    version: int


class StoredClaimData(BaseModel):
    """Stable read contract: field types without submission regex/date/business rules."""

    model_config = ConfigDict(extra="allow")
    patient_id: str
    first_name: str
    last_name: str
    provider_name: str
    provider_id: str
    service_date: str
    diagnosis_code: str
    procedure_code: str
    amount: str = Field(description="Stored claim charges in USD, represented as decimal text.")
    group_number: str = ""
    date_of_birth: str | None = None
    phone: str = ""
    email: str = ""
    npi: str = ""
    provider_address: str = ""
    claim_type: str = "Professional"
    service_type: str = "Medical"
    place_of_service: str = "Office"
    diagnosis_description: str = ""
    admission_date: str | None = None
    discharge_date: str | None = None
    prior_authorization: str = ""
    other_insurance: bool = False
    other_insurer: str = ""
    injury_type: str = "None"
    notes: str = ""
    synthetic_data_confirmed: bool = True


class ClaimDetail(ClaimSummary):
    data: StoredClaimData
    history: list[HistoryEntry]


class ClaimList(BaseModel):
    items: list[ClaimSummary]
    total: int
    offset: int
    limit: int


class IdentityResponse(BaseModel):
    subject: str
    roles: list[str]


class AnalyticsResponse(BaseModel):
    total: int
    total_amount: float
    approved_amount: float
    denied_amount: float
    approval_rate: int = Field(description="Percentage of all claims currently approved, including pending in denominator.")
    average_amount: float
    this_month: int
    by_status: dict[str, int]
    by_service: dict[str, int]
    by_month: dict[str, int]
    by_provider: dict[str, float]
