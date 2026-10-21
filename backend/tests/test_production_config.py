from cryptography.fernet import Fernet
from pydantic import ValidationError
import pytest
from app.core.config import Settings


def configuration(**overrides):
    values = dict(environment='production', debug=False,
        database_url='postgresql+asyncpg://example:example@database/example',
        jwt_secret='Dedicated-random-placeholder-for-configuration-test-only', encryption_key=Fernet.generate_key().decode(),
        cors_origins='https://trade.example.com', password_reset_frontend_url='https://trade.example.com',
        smtp_host='smtp.example.com', smtp_from_email='security@example.com', smtp_starttls=True)
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize('overrides',[
    {'debug':True}, {'jwt_secret':'short'}, {'encryption_key':'not-a-key'},
    {'database_url':'sqlite+aiosqlite:///test.db'}, {'cors_origins':'*'},
    {'cors_origins':'https://trade.example.com,https://other.example.com'},
    {'cors_origins':'http://trade.example.com'}, {'cors_origins':'https://trade.example.com/path'},
    {'smtp_host':None}, {'smtp_starttls':False,'smtp_ssl':False},
    {'password_reset_frontend_url':'https://attacker.invalid'}, {'access_token_expire_minutes':1440}
])
def test_unsafe_production_configuration_rejected(overrides):
    with pytest.raises(ValidationError): configuration(**overrides)


def test_valid_production_configuration_still_disables_live_execution():
    assert configuration(enable_live_trading=False).enable_live_trading is False


def test_invalid_configuration_does_not_echo_secrets_in_startup_error():
    secret='startup-secret-that-must-not-be-printed-1234567890'
    with pytest.raises(ValidationError) as error:
        configuration(jwt_secret=secret,debug=True)
    assert secret not in str(error.value)
