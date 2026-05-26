from typing import List
from app.modules.users.models import User, UserRole

def has_role(user: User, role: UserRole) -> bool:
    return role in user.role

def has_any_role(user: User, roles: List[UserRole]) -> bool:
    return any(r in user.role for r in roles)

def build_access_contexts(user: User) -> List[dict]:
    contexts = []
    
    for role in user.role:
        if role in [UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN]:
            contexts.append({
                "role": role,
                "scope_type": "GLOBAL",
                "company_id": None,
                "gas_station_id": None,
                "buyer_profile_id": None
            })
        elif role == UserRole.COMPANY_ADMIN:
            if user.company_id:
                contexts.append({
                    "role": role,
                    "scope_type": "COMPANY",
                    "company_id": user.company_id,
                    "gas_station_id": None,
                    "buyer_profile_id": None
                })
        elif role == UserRole.SPBU_ADMIN:
            if user.gas_station_id:
                contexts.append({
                    "role": role,
                    "scope_type": "GAS_STATION",
                    "company_id": None,
                    "gas_station_id": user.gas_station_id,
                    "buyer_profile_id": None
                })
        elif role == UserRole.SALES_OFFICER:
            if user.gas_station_id:
                contexts.append({
                    "role": role,
                    "scope_type": "GAS_STATION",
                    "company_id": None,
                    "gas_station_id": user.gas_station_id,
                    "buyer_profile_id": None
                })
        elif role == UserRole.BUYER:
            if user.buyer_profile:
                contexts.append({
                    "role": role,
                    "scope_type": "BUYER",
                    "company_id": None,
                    "gas_station_id": None,
                    "buyer_profile_id": user.buyer_profile.id
                })
                
    return contexts

def get_allowed_apps(roles: List[UserRole]) -> List[str]:
    apps = set()
    
    if any(r in roles for r in [UserRole.SUPER_ADMIN, UserRole.COMPANY_ADMIN, UserRole.SPBU_ADMIN, UserRole.GOV_ADMIN]):
        apps.add("ADMIN_WEB")
        
    if UserRole.SALES_OFFICER in roles:
        apps.add("POS_ANDROID")
        
    if UserRole.BUYER in roles:
        apps.add("BUYER_ANDROID")
        
    return list(apps)

def validate_client_access(user: User, client_type: str) -> bool:
    if client_type == "ADMIN_WEB":
        if has_role(user, UserRole.SUPER_ADMIN):
            return True
        if has_role(user, UserRole.COMPANY_ADMIN) and user.company_id is not None:
            return True
        if has_role(user, UserRole.SPBU_ADMIN) and user.gas_station_id is not None:
            return True
        if has_role(user, UserRole.GOV_ADMIN):
            return True
        return False
        
    elif client_type == "POS_ANDROID":
        if has_role(user, UserRole.SALES_OFFICER) and user.gas_station_id is not None:
            return True
        return False
        
    elif client_type == "BUYER_ANDROID":
        if has_role(user, UserRole.BUYER):
            return True
        return False
        
    return False
