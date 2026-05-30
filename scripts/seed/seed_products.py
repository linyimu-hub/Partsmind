#!/usr/bin/env python3
"""
scripts/seed/seed_products.py
──────────────────────────────
Seed the database with auto parts data.

生产级双语种子数据：
  - 产品名称：中文为主，附带英文翻译
  - description: 中英双语描述
  - embedding 输入：中英文混合，确保中英搜索都能命中
  - specs: 中文 key
  - 数据基于真实汽车零配件分类设计
"""

import argparse
import asyncio
import csv
import random
import sys
from pathlib import Path
from sqlalchemy.orm import selectinload 
# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.product import Product, ProductEmbedding
from app.services.embedding_service import embed_texts


# ── 双语数据模板 ────────────────────────────────────────────────────

CATEGORIES = {
    "brake": "刹车系统",
    "filter": "滤清器",
    "electrical": "电气系统",
    "suspension": "悬挂系统",
    "engine": "发动机",
    "transmission": "变速箱",
    "body": "车身配件",
    "cooling": "冷却系统",
}

BRANDS = ["Bosch 博世", "NGK", "Denso 电装", "ACDelco", "Monroe", "Bilstein",
          "Mann-Filter 曼牌", "Brembo 布雷博", "TRW", "SKF", "FAG", "Continental 大陆"]

VEHICLE_MAKES = [
    ("Toyota", "丰田"), ("Honda", "本田"), ("Ford", "福特"),
    ("BMW", "宝马"), ("Mercedes-Benz", "奔驰"), ("Volkswagen", "大众"),
    ("Nissan", "日产"), ("Hyundai", "现代"), ("Chevrolet", "雪佛兰"), ("Mazda", "马自达"),
]

MODELS_BY_MAKE = {
    "Toyota": [("Camry", "凯美瑞"), ("Corolla", "卡罗拉"), ("RAV4", "RAV4"), ("Highlander", "汉兰达"), ("Prius", "普锐斯")],
    "Honda":  [("Civic", "思域"), ("Accord", "雅阁"), ("CR-V", "CR-V"), ("Pilot", "皓影"), ("Fit", "飞度")],
    "Ford":   [("F-150", "F-150"), ("Mustang", "野马"), ("Explorer", "探险者"), ("Focus", "福克斯"), ("Escape", "翼虎")],
    "BMW":    [("3 Series", "3系"), ("5 Series", "5系"), ("X3", "X3"), ("X5", "X5"), ("7 Series", "7系")],
    "Mercedes-Benz": [("C-Class", "C级"), ("E-Class", "E级"), ("GLE", "GLE"), ("S-Class", "S级"), ("A-Class", "A级")],
    "Volkswagen": [("Golf", "高尔夫"), ("Passat", "帕萨特"), ("Tiguan", "途观"), ("Polo", "Polo"), ("Jetta", "捷达")],
    "Nissan": [("Altima", "天籁"), ("Sentra", "轩逸"), ("Rogue", "奇骏"), ("Pathfinder", "探路者"), ("Maxima", "千里马")],
    "Hyundai": [("Elantra", "伊兰特"), ("Sonata", "索纳塔"), ("Tucson", "途胜"), ("Santa Fe", "胜达"), ("Accent", "雅绅特")],
    "Chevrolet": [("Malibu", "迈锐宝"), ("Silverado", "索罗德"), ("Equinox", "Equinox"), ("Tahoe", "Tahoe"), ("Cruze", "科鲁兹")],
    "Mazda":  [("Mazda3", "马自达3 昂克赛拉"), ("Mazda6", "马自达6 阿特兹"), ("CX-5", "CX-5"), ("CX-9", "CX-9"), ("MX-5", "MX-5")],
}

# 零件中英双语数据 (name_cn, name_en, description_cn, description_en, search_keywords)
PARTS_BY_CATEGORY = {
    "brake": [
        ("陶瓷前刹车片", "Ceramic Front Brake Pad Set",
         "高性能陶瓷前刹车片套装，低粉尘，制动响应迅速", "High-performance ceramic front brake pad set, low-dust formula",
         ["刹车片", "前刹车片", "陶瓷刹车片", "brake pad", "ceramic"]),
        ("刹车盘 通风式", "Vented Brake Rotor",
         "通风式前刹车盘，散热性能优异，打孔设计提升制动效率", "Vented front brake disc, cross-drilled for heat dissipation",
         ["刹车盘", "刹车碟", "brake rotor", "brake disc", "通风刹车盘"]),
        ("刹车卡钳总成", "Brake Caliper Assembly",
         "再制造前刹车卡钳，含支架，性能与原厂一致", "Remanufactured front brake caliper with bracket",
         ["刹车卡钳", "卡钳", "brake caliper", "刹车钳"]),
        ("制动鼓", "Brake Drum",
         "后制动鼓，符合OEM技术规范", "Rear brake drum, OEM specification",
         ["制动鼓", "刹车鼓", "brake drum"]),
        ("制动总泵", "Brake Master Cylinder",
         "刹车总泵带储液罐，铸铁主体耐用可靠", "Brake master cylinder with reservoir",
         ["制动总泵", "刹车总泵", "master cylinder", "总泵"]),
    ],
    "filter": [
        ("机油滤清器", "Oil Filter",
         "旋装式机油滤清器，合成纤维滤芯，过滤精度高", "Spin-on oil filter, premium synthetic media",
         ["机油滤清器", "机滤", "oil filter", "机油格"]),
        ("空气滤清器", "Engine Air Filter",
         "高流量发动机空气滤清器，提升进气效率和动力", "Engine air filter, high-flow performance",
         ["空气滤清器", "空滤", "air filter", "空气格"]),
        ("空调滤清器", "Cabin Air Filter",
         "活性炭空调滤芯，过滤PM2.5和异味", "Cabin air/pollen filter with activated carbon",
         ["空调滤清器", "空调滤芯", "cabin filter", "空调格"]),
        ("燃油滤清器", "Fuel Filter",
         "管路式燃油滤清器，10微米过滤精度", "In-line fuel filter, 10 micron rating",
         ["燃油滤清器", "汽油滤", "fuel filter", "油格"]),
        ("自动变速箱滤芯套件", "Transmission Filter Kit",
         "自动变速箱滤芯套装，含密封垫片", "Automatic transmission filter kit with gasket",
         ["变速箱滤芯", "波箱滤芯", "transmission filter"]),
    ],
    "electrical": [
        ("铱金火花塞", "Iridium Spark Plug",
         "铱金火花塞，使用寿命达16万公里", "Iridium spark plug, 100,000 mile service life",
         ["火花塞", "铱金火花塞", "spark plug", "铱铂金"]),
        ("发电机", "Alternator",
         "再制造发电机，130A输出，原厂规格", "Remanufactured alternator, 130A output",
         ["发电机", "alternator", "充电机"]),
        ("起动机", "Starter Motor",
         "再制造起动机，高扭矩输出", "Remanufactured starter motor",
         ["起动机", "启动机", "starter motor", "马达"]),
        ("点火线圈", "Ignition Coil",
         "直接点火线圈总成，点火能量强", "Direct ignition coil pack",
         ["点火线圈", "高压包", "ignition coil"]),
        ("氧传感器", "Oxygen Sensor",
         "宽带前氧传感器，精确控制空燃比", "Upstream O2 sensor, wideband",
         ["氧传感器", "O2传感器", "oxygen sensor", "前氧传感器"]),
    ],
    "suspension": [
        ("减震器", "Shock Absorber",
         "充气式单筒减震器，操控稳定性强", "Gas-pressurized monotube shock absorber",
         ["减震器", "避震器", "shock absorber", "减振器"]),
        ("减震器总成", "Strut Assembly",
         "前减震器总成，含弹簧和顶胶", "Complete strut assembly with spring and mount",
         ["减震器总成", "前减震总成", "strut assembly", "麦弗逊"]),
        ("控制臂", "Control Arm",
         "前下控制臂，含球头", "Front lower control arm with ball joint",
         ["控制臂", "下摆臂", "control arm", "悬挂臂"]),
        ("转向拉杆球头", "Tie Rod End",
         "外转向拉杆球头，含防尘罩", "Outer tie rod end with boot",
         ["转向拉杆", "球头", "tie rod end", "转向球头"]),
        ("平衡杆连杆", "Sway Bar Link",
         "前防倾杆连接杆套件", "Front stabilizer bar link kit",
         ["平衡杆", "稳定杆", "sway bar link", "防倾杆"]),
    ],
    "engine": [
        ("正时皮带套件", "Timing Belt Kit",
         "正时皮带套装，含水泵和张紧轮", "Timing belt kit with water pump and tensioner",
         ["正时皮带", "timing belt", "正时套件"]),
        ("缸盖垫", "Head Gasket",
         "多层钢制缸盖垫片，密封性能优异", "Multi-layer steel head gasket",
         ["缸盖垫", "气缸垫", "head gasket"]),
        ("气门室盖垫", "Valve Cover Gasket",
         "气门室盖垫片套装，含密封圈", "Valve cover gasket set with grommets",
         ["气门室盖垫", "valve cover gasket"]),
        ("节温器", "Thermostat",
         "发动机冷却液节温器，带壳体", "Engine coolant thermostat with housing",
         ["节温器", "thermostat", "温控器"]),
        ("水泵", "Water Pump",
         "OEM规格水泵，含密封垫", "OEM-spec water pump with gasket",
         ["水泵", "water pump", "冷却泵"]),
    ],
    "transmission": [
        ("离合器套件", "Clutch Kit",
         "完整离合器套装：压盘、从动盘、分离轴承", "Complete clutch kit: disc, pressure plate, bearing",
         ["离合器", "clutch kit", "离合器套件"]),
        ("半轴总成", "CV Axle Shaft",
         "再制造前半轴，含防尘罩", "Remanufactured front CV axle with boots",
         ["半轴", "CV轴", "传动轴", "axle shaft"]),
        ("变速箱悬置", "Transmission Mount",
         "液压式发动机/变速箱悬置", "Engine/transmission mount, hydraulic",
         ["变速箱悬置", "transmission mount", "波箱脚胶"]),
        ("换挡拉线", "Shift Cable",
         "自动变速箱换挡拉线", "Automatic transmission shifter cable",
         ["换挡拉线", "shift cable", "波箱拉线"]),
        ("差速器油封", "Differential Seal",
         "后差速器输出轴油封", "Rear differential output shaft seal",
         ["差速器油封", "油封", "differential seal"]),
    ],
    "body": [
        ("电动折叠后视镜", "Power-folding Side Mirror",
         "电动折叠后视镜，带加热功能", "Power-folding side mirror, heated",
         ["后视镜", "side mirror", "倒车镜"]),
        ("雨刮片", "Windshield Wiper Blade",
         "全季节软骨雨刮片", "All-season beam wiper blade",
         ["雨刮", "雨刮片", "wiper blade"]),
        ("发动机盖撑杆", "Hood Strut",
         "发动机盖气压撑杆，一对", "Gas hood support strut, pair",
         ["发动机盖撑杆", "引擎盖撑杆", "hood strut"]),
        ("车门把手", "Door Handle",
         "外车门把手，与原车同色", "Exterior door handle, painted to match",
         ["车门把手", "门把手", "door handle"]),
        ("LED大灯总成", "LED Headlight Assembly",
         "LED大灯总成，即插即用，无需改装", "LED headlight assembly, plug-and-play",
         ["大灯", "前大灯", "LED大灯", "headlight", "headlamp"]),
    ],
    "cooling": [
        ("散热器", "Radiator",
         "全铝散热器，原厂尺寸", "Aluminum core radiator, OEM fit",
         ["散热器", "水箱", "radiator", "冷却水箱"]),
        ("散热器风扇", "Cooling Fan Assembly",
         "电子散热风扇总成", "Electric radiator cooling fan assembly",
         ["散热风扇", "冷却风扇", "cooling fan", "电子扇"]),
        ("副水箱", "Coolant Reservoir",
         "冷却液副水箱/膨胀水箱", "Overflow coolant reservoir/expansion tank",
         ["副水箱", "膨胀水箱", "coolant reservoir"]),
        ("散热器水管 上水管", "Upper Radiator Hose",
         "硅胶上水管，耐高温", "Upper radiator hose, silicone",
         ["散热器水管", "上水管", "radiator hose", "冷却水管"]),
        ("暖风水箱", "Heater Core",
         "暖风水箱总成", "Replacement heater core",
         ["暖风水箱", "暖风", "heater core"]),
    ],
}

SPECS_BY_CATEGORY = {
    "brake": lambda: {
        "厚度_mm": round(random.uniform(8, 20), 1),
        "材质": random.choice(["陶瓷", "半金属", "有机"]),
        "位置": random.choice(["前", "后"]),
        "含安装配件": random.choice([True, False]),
    },
    "filter": lambda: {
        "过滤精度_微米": random.choice([5, 10, 20, 40]),
        "螺纹规格": random.choice(["M20x1.5", "M22x1.5", "3/4-16 UNF"]),
        "高度_mm": random.randint(60, 120),
    },
    "electrical": lambda: {
        "电压": "12V",
        "间隙_mm": round(random.uniform(0.6, 1.1), 2),
        "螺纹规格": random.choice(["14mm", "12mm"]),
    },
    "suspension": lambda: {
        "弹簧刚度_N_mm": round(random.uniform(15, 35), 1),
        "行程_mm": random.randint(80, 150),
        "位置": random.choice(["前左", "前右", "后左", "后右"]),
    },
    "engine": lambda: {"材质": random.choice(["钢", "铝合金", "复合材料"])},
    "transmission": lambda: {"类型": random.choice(["手动", "自动", "CVT"])},
    "body": lambda: {"颜色": random.choice(["黑色", "银色", "底漆", "原车色"])},
    "cooling": lambda: {
        "容量_升": round(random.uniform(4, 12), 1),
        "芯体材质": random.choice(["铝合金", "铜黄铜"]),
    },
}


def generate_compatible_vehicles(count: int = 3) -> list[dict]:
    """生成随机适配车型 — 双语 make/model"""
    vehicles = []
    makes = random.sample(VEHICLE_MAKES, min(count, len(VEHICLE_MAKES)))
    for make_en, make_cn in makes:
        models = MODELS_BY_MAKE[make_en]
        model_en, model_cn = random.choice(models)
        year_from = random.randint(2010, 2020)
        year_to = year_from + random.randint(3, 8)
        vehicles.append({
            "make": f"{make_en} {make_cn}",
            "model": f"{model_en} {model_cn}",
            "year_from": year_from,
            "year_to": min(year_to, 2024),
        })
    return vehicles


def generate_synthetic_products(count: int = 200) -> list[dict]:
    """生成中英双语合成产品数据"""
    products = []
    used_part_numbers: set[str] = set()

    for _ in range(count):
        category_en = random.choice(list(CATEGORIES.keys()))
        category_cn = CATEGORIES[category_en]
        part_name_cn, part_name_en, desc_cn, desc_en, keywords = random.choice(PARTS_BY_CATEGORY[category_en])
        brand = random.choice(BRANDS)
        brand_short = brand.split(" ")[0]

        while True:
            prefix = category_en[:3].upper()
            part_number = f"{prefix}-{brand_short[:2].upper()}-{random.randint(10000, 99999)}"
            if part_number not in used_part_numbers:
                used_part_numbers.add(part_number)
                break

        spec_fn = SPECS_BY_CATEGORY.get(category_en, lambda: {})

        # 产品名以中文为主，附带英文
        full_name = f"{brand} {part_name_cn} / {part_name_en}"

        products.append({
            "part_number": part_number,
            "name": full_name,
            # description 中英双语
            "description": f"{desc_cn}。{desc_en}",
            "category": f"{category_cn} / {category_en}",
            "brand": brand,
            "compatible_vehicles": generate_compatible_vehicles(random.randint(1, 4)),
            "specs": spec_fn(),
            "price": round(random.uniform(15, 850), 2),
            "stock": random.randint(0, 200),
            "image_url": None,
            # 额外字段：embedding 时用
            "_keywords": keywords,
        })

    return products


def build_embedding_text(p: Product, extra_keywords: list[str] | None = None) -> str:
    """为产品构建用于 embedding 的丰富文本（中英混合）"""
    compat_strs = []
    for v in (p.compatible_vehicles or []):
        compat_strs.append(f"{v['make']} {v['model']} {v['year_from']}-{v['year_to']}")
    compat_str = "; ".join(compat_strs)

    # 关键词从 specs 提取
    spec_str = " ".join(str(v) for v in (p.specs or {}).values())

    parts = [
        p.name or "",
        p.description or "",
        f"零件号 part number: {p.part_number}",
        f"品牌 brand: {p.brand or ''}",
        f"类别 category: {p.category}",
        f"适配车型 fits: {compat_str}",
        f"规格 specs: {spec_str}",
    ]
    if extra_keywords:
        parts.append("关键词 keywords: " + " ".join(extra_keywords))

    return ". ".join(p for p in parts if p)


async def seed(products_data: list[dict], embed: bool = False) -> None:
    engine = create_async_engine(settings.database_url)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        print(f"Seeding {len(products_data)} products...")
        inserted = 0

        # 关键词暂存（不写入 DB 的 specs 字段）
        keywords_by_partnum: dict[str, list[str]] = {}

        for data in products_data:
            keywords = data.pop("_keywords", [])
            product = Product(
                part_number=data["part_number"],
                name=data["name"],
                description=data.get("description"),
                category=data["category"],
                brand=data.get("brand"),
                compatible_vehicles=data.get("compatible_vehicles", []),
                specs=data.get("specs", {}),
                price=data.get("price"),
                stock=data.get("stock", 0),
                image_url=data.get("image_url"),
            )
            db.add(product)
            inserted += 1
            keywords_by_partnum[product.part_number] = keywords

        await db.commit()
        print(f"✅ Inserted {inserted} products")

        if embed:
            from sqlalchemy import select
            print("Generating embeddings (中英双语向量化)...")
            result = await db.execute(
                select(Product)
                .options(selectinload(Product.compatible_vehicles))
                .where(Product.id.notin_(
                    select(ProductEmbedding.product_id)
                ))
            )
            products = result.scalars().all()

            texts = []
            for p in products:
                texts.append(build_embedding_text(p, keywords_by_partnum.get(p.part_number)))

            vectors = await embed_texts(texts)

            for product, vector in zip(products, vectors):
                emb = ProductEmbedding(
                    product_id=product.id,
                    embedding=vector,
                    embed_type="text",
                )
                db.add(emb)

            await db.commit()
            print(f"✅ Generated {len(vectors)} embeddings")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--csv", type=str)
    parser.add_argument("--embed", action="store_true")
    args = parser.parse_args()

    if args.synthetic:
        products = generate_synthetic_products(args.count)
        print(f"Generated {len(products)} bilingual products")
    elif args.csv:
        with open(args.csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            products = list(reader)
        print(f"Loaded {len(products)} products from CSV")
    else:
        parser.print_help()
        sys.exit(1)

    asyncio.run(seed(products, embed=args.embed))
