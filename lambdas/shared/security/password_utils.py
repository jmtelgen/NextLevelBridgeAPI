import bcrypt
import secrets
import string
import base64
from typing import Tuple

class PasswordUtils:
    """
    Utility class for password operations with bcrypt and enhanced salt
    """
    
    @staticmethod
    def hash_password(password: str) -> Tuple[str, str]:
        """
        Hash a password using bcrypt with enhanced salt
        
        Args:
            password: The plaintext password to hash
            
        Returns:
            tuple: (hashed_password, salt)
        """
        # Generate additional salt for enhanced security
        salt = PasswordUtils.generate_salt()
        
        # Combine password with salt before hashing
        salted_password = password + salt
        
        # Use bcrypt to hash the salted password (bcrypt adds its own salt automatically)
        hashed = bcrypt.hashpw(salted_password.encode('utf-8'), bcrypt.gensalt())
        
        return hashed.decode('utf-8'), salt
    
    @staticmethod
    def verify_password(password: str, hashed_password: str, salt: str) -> bool:
        """
        Verify a password against its hash with salt
        
        Args:
            password: The plaintext password to verify
            hashed_password: The hashed password to check against
            salt: The salt used during hashing
            
        Returns:
            bool: True if password matches, False otherwise
        """
        try:
            # Recreate the salted password
            salted_password = password + salt
            
            # Verify using bcrypt
            return bcrypt.checkpw(salted_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception:
            return False
    
    @staticmethod
    def generate_salt(length: int = 16) -> str:
        """
        Generate a random salt for enhanced security
        
        Args:
            length: Length of the salt to generate
            
        Returns:
            str: Base64 encoded salt
        """
        salt_bytes = secrets.token_bytes(length)
        return base64.b64encode(salt_bytes).decode('utf-8')
    
    @staticmethod
    def generate_secure_password(length: int = 12) -> str:
        """
        Generate a secure random password
        
        Args:
            length: Length of the password to generate
            
        Returns:
            str: Generated password
        """
        # Define character sets
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        digits = string.digits
        symbols = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        
        # Ensure at least one character from each set
        password = [
            secrets.choice(lowercase),
            secrets.choice(uppercase),
            secrets.choice(digits),
            secrets.choice(symbols)
        ]
        
        # Fill the rest with random characters
        all_chars = lowercase + uppercase + digits + symbols
        password.extend(secrets.choice(all_chars) for _ in range(length - 4))
        
        # Shuffle the password
        password_list = list(password)
        secrets.SystemRandom().shuffle(password_list)
        
        return ''.join(password_list)
    
    @staticmethod
    def validate_password_strength(password: str) -> Tuple[bool, str]:
        """
        Validate password strength
        
        Args:
            password: The password to validate
            
        Returns:
            tuple: (is_valid, error_message)
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        if len(password) > 128:
            return False, "Password must be no more than 128 characters long"
        
        # Check for at least one lowercase letter
        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"
        
        # Check for at least one uppercase letter
        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"
        
        # Check for at least one digit
        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit"
        
        # Check for at least one special character
        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in special_chars for c in password):
            return False, "Password must contain at least one special character"
        
        return True, "Password meets strength requirements"
