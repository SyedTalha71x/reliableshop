# services/database_config.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from contextlib import contextmanager
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Singleton pattern for database connection pool"""
    
    _instance = None
    _pool = None
    _tables_initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialize_pool()
        return cls._instance
    
    def _initialize_pool(self):
        """Initialize connection pool with production settings"""
        try:
            self._pool = SimpleConnectionPool(
                minconn=2,
                maxconn=20,
                host=os.getenv('DB_HOST', 'localhost'),
                port=os.getenv('DB_PORT', '5432'),
                database=os.getenv('DB_NAME', 'ecommerce'),
                user=os.getenv('DB_USER', 'microservice'),
                password=os.getenv('DB_PASSWORD', 'secure_password_123'),
                connect_timeout=5,
                options='-c statement_timeout=30000'
            )
            logger.info("✅ Database connection pool created successfully")
        except Exception as e:
            logger.error(f"❌ Failed to create database pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """Get connection from pool"""
        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                self._pool.putconn(conn)
    
    @contextmanager
    def get_cursor(self, dict_cursor=True):
        """Get cursor with automatic commit"""
        with self.get_connection() as conn:
            if dict_cursor:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    yield cur
                    conn.commit()
            else:
                with conn.cursor() as cur:
                    yield cur
                    conn.commit()
    
    def init_tables(self):
        if self._tables_initialized:
            return
            
        try:
            with self.get_cursor() as cur:
                # Create schema if not exists
                cur.execute("CREATE SCHEMA IF NOT EXISTS ecommerce")
                
                # Carts table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS carts (
                        user_id VARCHAR(100) PRIMARY KEY,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Cart items table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS cart_items (
                        id SERIAL PRIMARY KEY,
                        user_id VARCHAR(100) REFERENCES carts(user_id) ON DELETE CASCADE,
                        product_id INTEGER NOT NULL,
                        quantity INTEGER DEFAULT 1,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, product_id)
                    )
                """)
                
                # Orders table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        order_id VARCHAR(50) PRIMARY KEY,
                        user_id VARCHAR(100) NOT NULL,
                        status VARCHAR(50) DEFAULT 'pending',
                        total_amount DECIMAL(10, 2),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Order items table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS order_items (
                        id SERIAL PRIMARY KEY,
                        order_id VARCHAR(50) REFERENCES orders(order_id) ON DELETE CASCADE,
                        product_id INTEGER NOT NULL,
                        quantity INTEGER NOT NULL,
                        price_at_time DECIMAL(10, 2),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Payment transactions table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS payments (
                        transaction_id VARCHAR(50) PRIMARY KEY,
                        order_id VARCHAR(50),
                        amount DECIMAL(10, 2),
                        status VARCHAR(20),
                        payment_method VARCHAR(50),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create indexes for performance
                cur.execute("CREATE INDEX IF NOT EXISTS idx_cart_items_user_id ON cart_items(user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id)")
                
                self._tables_initialized = True
                logger.info("Database tables initialized successfully")
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise

# Global instance
db = DatabaseManager()

# Initialize tables immediately
db.init_tables()