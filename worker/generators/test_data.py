import os
import secrets
from dataclasses import dataclass

try:
    from .phone_generator import generate_phone
except ImportError:
    from worker.generators.phone_generator import generate_phone


DEFAULT_STATIC_NAME = os.getenv("DEFAULT_STATIC_NAME", "")
DEFAULT_STATIC_PASSWORD = os.getenv("DEFAULT_STATIC_PASSWORD", "SecurePass@123")
DEFAULT_STATIC_PLACE = os.getenv("DEFAULT_STATIC_PLACE", "")
DEFAULT_STATIC_LANGUAGE = os.getenv("DEFAULT_STATIC_LANGUAGE", "en")

FIRST_NAMES = [
    "Rahul", "Rohit", "Amit", "Suresh", "Kiran", "Vikas", "Pooja", "Sneha",
    "Anil", "Arjun", "Deepak", "Manoj", "Priya", "Sunil", "Rajesh", "Varun",
    "Naveen", "Aditya", "Ramesh", "Sanjay", "Karthik", "Manish", "Gaurav",
    "Pradeep", "Harish", "Sachin", "Vijay", "Anand", "Ravi", "Sandip",
    "Divya", "Swati", "Neha", "Megha", "Ananya", "Ritu", "Preeti", "Kavita",
    "Ashok", "Ganesh", "Santosh", "Ajay", "Mohan", "Rakesh", "Alok", "Prakash",
]

LAST_NAMES = [
    "Kumar", "Sharma", "Reddy", "Verma", "Patel", "Singh", "Rao", "Mehta",
    "Gupta", "Joshi", "Nair", "Yadav", "Mishra", "Choudhary", "Kulkarni",
    "Das", "Deshmukh", "Bhat", "Iyer", "Pillai", "Naidu", "Chauhan", "Agarwal",
    "Saxena", "Pandey", "Tripathi", "Shukla", "Bose", "Ghosh", "Mukherjee",
]

PLACES = [
    "Hyderabad", "Bengaluru", "Mumbai", "Pune", "Chennai", "Delhi", "Kolkata",
    "Ahmedabad", "Jaipur", "Lucknow", "Visakhapatnam", "Vijayawada", "Coimbatore",
    "Surat", "Nagpur", "Indore", "Bhopal", "Thane", "Patna", "Vadodara",
    "Kochi", "Chandigarh", "Mysuru", "Bhubaneswar", "Dehradun", "Ranchi",
]


def generate_random_name() -> str:
    if DEFAULT_STATIC_NAME:
        return DEFAULT_STATIC_NAME
    return f"{secrets.choice(FIRST_NAMES)} {secrets.choice(LAST_NAMES)}"


def generate_random_place() -> str:
    if DEFAULT_STATIC_PLACE:
        return DEFAULT_STATIC_PLACE
    return secrets.choice(PLACES)


@dataclass(frozen=True)
class TestIdentity:
    __test__ = False
    account_id: str
    name: str = ""
    test_id: str = ""
    phone: str = ""
    password: str = DEFAULT_STATIC_PASSWORD
    place: str = ""
    language: str = DEFAULT_STATIC_LANGUAGE
    referral: str = ""


def generate_identity(index: int, referral: str = "") -> TestIdentity:
    return TestIdentity(
        account_id=f"TEST{index:03d}",
        name=generate_random_name(),
        test_id=f"ident-{index:04d}",
        phone=generate_phone(index),
        password=DEFAULT_STATIC_PASSWORD,
        place=generate_random_place(),
        language=DEFAULT_STATIC_LANGUAGE,
        referral=referral,
    )

