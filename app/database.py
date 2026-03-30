from contextlib import contextmanager

import pymysql

from app import config


def get_mysql_config() -> dict:
    return {
        "host": config.MYSQL_HOST,
        "port": config.MYSQL_PORT,
        "user": config.MYSQL_USER,
        "password": config.MYSQL_PASSWORD,
        "database": config.MYSQL_DATABASE,
        "charset": config.MYSQL_CHARSET,
        "autocommit": True,
    }


def _get_mysql_config_without_db() -> dict:
    return {
        "host": config.MYSQL_HOST,
        "port": config.MYSQL_PORT,
        "user": config.MYSQL_USER,
        "password": config.MYSQL_PASSWORD,
        "charset": config.MYSQL_CHARSET,
        "autocommit": True,
    }


@contextmanager
def get_conn():
    """获取数据库连接的上下文管理器，退出时自动关闭连接"""
    conn = pymysql.connect(**get_mysql_config())
    try:
        yield conn
    finally:
        conn.close()


def create_database_if_not_exists():
    """自动创建数据库（如果不存在）"""
    connection = pymysql.connect(**_get_mysql_config_without_db())
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{config.MYSQL_DATABASE}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            print(f"数据库 '{config.MYSQL_DATABASE}' 检查/创建完成")
    finally:
        connection.close()


TABLE_STATEMENTS = [
     # 用户表（用于用户认证）
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '用户ID',
        username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
        hashed_password VARCHAR(255) NOT NULL COMMENT 'bcrypt 加密后的密码',
        real_name VARCHAR(50) COMMENT '真实姓名',
        role ENUM('admin', 'user') NOT NULL DEFAULT 'user' COMMENT '角色',
        phone VARCHAR(20) COMMENT '手机号',
        email VARCHAR(100) COMMENT '邮箱',
        is_active TINYINT(1) DEFAULT 1 COMMENT '是否启用：1-启用 0-禁用',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_username (username)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';
    """,
    # 品类字典表
    """
    CREATE TABLE IF NOT EXISTS dict_categories (
        row_id INT AUTO_INCREMENT PRIMARY KEY COMMENT '行主键（自增，唯一）',
        category_id INT NOT NULL COMMENT '品类分组ID（多名称共用同一值，如铜=301）',
        category_code VARCHAR(20) NOT NULL UNIQUE COMMENT '品类业务码（如：CAT_CU），不随名称变化',
        name VARCHAR(50) NOT NULL UNIQUE COMMENT '品类名称（如：紫铜、黄铜）',
        is_main TINYINT(1) DEFAULT 0 COMMENT '是否主品类：1-是（用于比价表展示），0-否',
        is_active TINYINT(1) DEFAULT 1 COMMENT '是否启用',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_category_id (category_id),
        INDEX idx_category_main (category_id, is_main),
        INDEX idx_is_main (is_main)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='品类字典表（多名称共用同一category_id）';
    """,
    # 仓库字典表
    """
    CREATE TABLE IF NOT EXISTS dict_warehouses (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '行主键（自增，唯一）',
        warehouse_code VARCHAR(20) NOT NULL UNIQUE COMMENT '仓库业务码（如：WH_SH），不随名称变化',
        name VARCHAR(100) NOT NULL UNIQUE COMMENT '仓库名称',
        location VARCHAR(100) COMMENT '仓库地址',
        is_active TINYINT(1) DEFAULT 1 COMMENT '是否启用',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仓库字典表';
    """,
    # 冶炼厂字典表
    """
    CREATE TABLE IF NOT EXISTS dict_factories (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '行主键（自增，唯一）',
        factory_code VARCHAR(20) NOT NULL UNIQUE COMMENT '冶炼厂业务码（如：FAC_BJ），不随名称变化',
        name VARCHAR(100) NOT NULL UNIQUE COMMENT '冶炼厂名称',
        location VARCHAR(100) COMMENT '地点',
        contact VARCHAR(50) COMMENT '联系人',
        phone VARCHAR(30) COMMENT '联系电话',
        is_active TINYINT(1) DEFAULT 1 COMMENT '是否启用',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='冶炼厂字典表';
    """,
    # 运费价格表
    """
    CREATE TABLE IF NOT EXISTS freight_rates (
        id INT AUTO_INCREMENT PRIMARY KEY,
        factory_id INT NOT NULL COMMENT '冶炼厂ID',
        warehouse_id INT NOT NULL COMMENT '仓库ID',
        price_per_ton DECIMAL(10, 2) NOT NULL COMMENT '每吨运费（元）',
        effective_date DATE NOT NULL COMMENT '生效日期',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_freight_factory FOREIGN KEY (factory_id) REFERENCES dict_factories (id) ON UPDATE CASCADE ON DELETE RESTRICT,
        CONSTRAINT fk_freight_warehouse FOREIGN KEY (warehouse_id) REFERENCES dict_warehouses (id) ON UPDATE CASCADE ON DELETE RESTRICT,
        UNIQUE KEY uk_factory_warehouse_date (factory_id, warehouse_id, effective_date),
        INDEX idx_effective_date (effective_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='运费价格表';
    """,
    # 报价表元数据表（存储报价表的整体信息）
    """
    CREATE TABLE IF NOT EXISTS quote_table_metadata (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '报价表ID',
        factory_id INT NOT NULL COMMENT '冶炼厂ID',
        quote_date DATE NOT NULL COMMENT '报价日期',
        execution_date VARCHAR(50) COMMENT '执行日期（如：2026年3月17日）',
        doc_title VARCHAR(200) COMMENT '文档标题（如：废铅酸蓄电池回收价格报价表）',
        price_unit VARCHAR(50) DEFAULT '元/吨' COMMENT '价格单位',
        has_merged_cells TINYINT(1) DEFAULT 0 COMMENT '是否有合并单元格',
        vat_columns_detected JSON COMMENT '检测到的VAT列类型（JSON数组）',
        raw_full_text LONGTEXT COMMENT '原始完整识别文本',
        markdown_table LONGTEXT COMMENT 'Markdown格式的表格',
        processing_time DECIMAL(10, 2) COMMENT '处理耗时（秒）',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_metadata_factory FOREIGN KEY (factory_id) REFERENCES dict_factories (id) ON UPDATE CASCADE ON DELETE RESTRICT,
        UNIQUE KEY uk_factory_quote_date (factory_id, quote_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报价表元数据表';
    """,
    # 报价明细表（优化版本）
    """
    CREATE TABLE IF NOT EXISTS quote_details (
        id INT AUTO_INCREMENT PRIMARY KEY,
        metadata_id INT NOT NULL COMMENT '报价表元数据ID',
        category_id INT NOT NULL COMMENT '品类ID',
        raw_category_name VARCHAR(100) NOT NULL COMMENT '原始品类名',
        unit_price DECIMAL(10, 2) NOT NULL COMMENT '单价（元/吨）',
        price_1pct_vat DECIMAL(10, 2) COMMENT '1%增值税价格',
        price_3pct_vat DECIMAL(10, 2) COMMENT '3%增值税价格',
        price_13pct_vat DECIMAL(10, 2) COMMENT '13%增值税价格',
        price_normal_invoice DECIMAL(10, 2) COMMENT '普通发票价格',
        price_reverse_invoice DECIMAL(10, 2) COMMENT '反向发票价格',
        remark VARCHAR(500) COMMENT '备注（如：均为控水价格）',
        raw_text VARCHAR(500) COMMENT '原始识别文本',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_metadata_category (metadata_id, category_id),
        CONSTRAINT fk_detail_metadata FOREIGN KEY (metadata_id) REFERENCES quote_table_metadata (id) ON UPDATE CASCADE ON DELETE CASCADE,
        CONSTRAINT fk_detail_category FOREIGN KEY (category_id) REFERENCES dict_categories (row_id) ON UPDATE CASCADE ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报价明细表（优化版本）';
    """,
    # 报价表规则和备注表
    """
    CREATE TABLE IF NOT EXISTS quote_table_rules (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '规则ID',
        metadata_id INT NOT NULL COMMENT '报价表元数据ID',
        rule_type ENUM('footer_note', 'policy', 'brand_spec') DEFAULT 'footer_note' COMMENT '规则类型',
        rule_order INT DEFAULT 0 COMMENT '规则顺序',
        rule_content TEXT NOT NULL COMMENT '规则内容',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_rule_metadata FOREIGN KEY (metadata_id) REFERENCES quote_table_metadata (id) ON UPDATE CASCADE ON DELETE CASCADE,
        INDEX idx_metadata_type (metadata_id, rule_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报价表规则和备注表';
    """,
    # 仓库库存表（最小化：仓库+品类+可用吨数）
    """
    CREATE TABLE IF NOT EXISTS warehouse_inventories (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '行主键',
        warehouse_id INT NOT NULL COMMENT '仓库ID',
        category_id INT NOT NULL COMMENT '品类行ID（关联dict_categories.row_id）',
        available_tons DECIMAL(10, 3) NOT NULL DEFAULT 0 COMMENT '当前可用吨数',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_inventory_warehouse FOREIGN KEY (warehouse_id) REFERENCES dict_warehouses (id) ON UPDATE CASCADE ON DELETE RESTRICT,
        CONSTRAINT fk_inventory_category FOREIGN KEY (category_id) REFERENCES dict_categories (row_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        UNIQUE KEY uk_inventory_warehouse_category (warehouse_id, category_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仓库库存表';
    """,
    # 冶炼厂需求主表（最小化：按天配置）
    """
    CREATE TABLE IF NOT EXISTS factory_demands (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '需求主表ID',
        factory_id INT NOT NULL COMMENT '冶炼厂ID',
        demand_date DATE NOT NULL COMMENT '需求日期',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_demand_factory FOREIGN KEY (factory_id) REFERENCES dict_factories (id) ON UPDATE CASCADE ON DELETE RESTRICT,
        UNIQUE KEY uk_factory_demand_date (factory_id, demand_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='冶炼厂需求主表';
    """,
    # 冶炼厂需求明细表（最小化：品类+吨数）
    """
    CREATE TABLE IF NOT EXISTS factory_demand_items (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '需求明细ID',
        demand_id INT NOT NULL COMMENT '需求主表ID',
        category_id INT NOT NULL COMMENT '品类行ID（关联dict_categories.row_id）',
        required_tons DECIMAL(10, 3) NOT NULL DEFAULT 0 COMMENT '需求吨数',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_demand_item_demand FOREIGN KEY (demand_id) REFERENCES factory_demands (id) ON UPDATE CASCADE ON DELETE CASCADE,
        CONSTRAINT fk_demand_item_category FOREIGN KEY (category_id) REFERENCES dict_categories (row_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        UNIQUE KEY uk_demand_category (demand_id, category_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='冶炼厂需求明细表';
    """,

]


def create_tables() -> None:
    create_database_if_not_exists()
    config_dict = get_mysql_config()
    connection = pymysql.connect(**config_dict)
    try:
        with connection.cursor() as cursor:
            for statement in TABLE_STATEMENTS:
                cursor.execute(statement)
        connection.commit()
        print("所有数据表创建完成")
    finally:
        connection.close()


if __name__ == "__main__":
    create_tables()
