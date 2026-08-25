"""The synthetic Atlas catalog, customer list and order book.

FICTIONAL DATA. Atlas Industrial Supply does not exist. Every SKU, price,
customer, contact, order and shipment below was invented for this demo.

Two design notes:

1. SKUs are short and numeric (`ATL-1042`) because the agent has to read them
   aloud. `FST-SHCS-M8X30-A2-70` is unspeakable over a phone line.

2. The catalog contains *deliberate* ambiguity. Four stainless M8 socket-head
   screws differ only by length; three chemical-resistant gloves differ only by
   material. A caller asking for "M8 stainless screws" cannot be served without
   a clarifying question, which is the behaviour the evals check for.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Products: (sku, name, description, category, uom, unit_price, attributes,
#            search_terms)
# ---------------------------------------------------------------------------

PRODUCTS: list[dict] = [
    # --- Fasteners: socket-head cap screws -------------------------------
    # Four stainless variants differing only by length -> ambiguity by design.
    {
        "sku": "ATL-1020",
        "name": "M8 x 20mm Stainless Socket-Head Cap Screw",
        "description": "A2-70 stainless steel socket-head cap screw, M8-1.25 thread, 20mm length.",
        "category": "Fasteners",
        "unit_of_measure": "each",
        "unit_price": 0.62,
        "attributes": {
            "thread_size": "M8-1.25",
            "length_mm": 20,
            "material": "304 stainless steel",
            "head_style": "socket head cap",
            "finish": "plain",
        },
        "search_terms": "m8 bolt screw cap screw allen socket head stainless ss hex drive metric",
    },
    {
        "sku": "ATL-1030",
        "name": "M8 x 30mm Stainless Socket-Head Cap Screw",
        "description": "A2-70 stainless steel socket-head cap screw, M8-1.25 thread, 30mm length.",
        "category": "Fasteners",
        "unit_of_measure": "each",
        "unit_price": 0.71,
        "attributes": {
            "thread_size": "M8-1.25",
            "length_mm": 30,
            "material": "304 stainless steel",
            "head_style": "socket head cap",
            "finish": "plain",
        },
        "search_terms": "m8 bolt screw cap screw allen socket head stainless ss hex drive metric",
    },
    {
        "sku": "ATL-1040",
        "name": "M8 x 40mm Stainless Socket-Head Cap Screw",
        "description": "A2-70 stainless steel socket-head cap screw, M8-1.25 thread, 40mm length.",
        "category": "Fasteners",
        "unit_of_measure": "each",
        "unit_price": 0.84,
        "attributes": {
            "thread_size": "M8-1.25",
            "length_mm": 40,
            "material": "304 stainless steel",
            "head_style": "socket head cap",
            "finish": "plain",
        },
        "search_terms": "m8 bolt screw cap screw allen socket head stainless ss hex drive metric",
    },
    {
        "sku": "ATL-1050",
        "name": "M8 x 50mm Stainless Socket-Head Cap Screw",
        "description": "A2-70 stainless steel socket-head cap screw, M8-1.25 thread, 50mm length.",
        "category": "Fasteners",
        "unit_of_measure": "each",
        "unit_price": 0.98,
        "attributes": {
            "thread_size": "M8-1.25",
            "length_mm": 50,
            "material": "304 stainless steel",
            "head_style": "socket head cap",
            "finish": "plain",
        },
        "search_terms": "m8 bolt screw cap screw allen socket head stainless ss hex drive metric",
    },
    {
        "sku": "ATL-1031",
        "name": "M8 x 30mm Zinc-Plated Socket-Head Cap Screw",
        "description": "Class 12.9 alloy steel socket-head cap screw, zinc-plated, M8-1.25 thread, 30mm length.",
        "category": "Fasteners",
        "unit_of_measure": "each",
        "unit_price": 0.38,
        "attributes": {
            "thread_size": "M8-1.25",
            "length_mm": 30,
            "material": "alloy steel",
            "head_style": "socket head cap",
            "finish": "zinc plated",
        },
        "search_terms": "m8 bolt screw cap screw allen socket head zinc plated steel metric",
    },
    {
        "sku": "ATL-1130",
        "name": "M10 x 30mm Stainless Socket-Head Cap Screw",
        "description": "A2-70 stainless steel socket-head cap screw, M10-1.5 thread, 30mm length.",
        "category": "Fasteners",
        "unit_of_measure": "each",
        "unit_price": 1.06,
        "attributes": {
            "thread_size": "M10-1.5",
            "length_mm": 30,
            "material": "304 stainless steel",
            "head_style": "socket head cap",
            "finish": "plain",
        },
        "search_terms": "m10 bolt screw cap screw allen socket head stainless ss metric",
    },
    {
        "sku": "ATL-1210",
        "name": "M8 x 30mm Stainless Hex-Head Bolt",
        "description": "A2-70 stainless steel hex-head bolt, M8-1.25 thread, 30mm length.",
        "category": "Fasteners",
        "unit_of_measure": "each",
        "unit_price": 0.58,
        "attributes": {
            "thread_size": "M8-1.25",
            "length_mm": 30,
            "material": "304 stainless steel",
            "head_style": "hex head",
            "finish": "plain",
        },
        "search_terms": "m8 bolt hex head stainless ss metric wrench",
    },
    # --- Fasteners: washers and nuts -------------------------------------
    {
        "sku": "ATL-1310",
        "name": "M8 Stainless Flat Washer",
        "description": "304 stainless steel flat washer for M8 fasteners, 8.4mm ID, 16mm OD.",
        "category": "Fasteners",
        "unit_of_measure": "each",
        "unit_price": 0.09,
        "attributes": {
            "fits_thread": "M8",
            "material": "304 stainless steel",
            "inner_diameter_mm": 8.4,
            "outer_diameter_mm": 16.0,
            "type": "flat washer",
        },
        "search_terms": "m8 washer flat washers stainless ss metric",
    },
    {
        "sku": "ATL-1311",
        "name": "M8 Zinc-Plated Flat Washer",
        "description": "Zinc-plated steel flat washer for M8 fasteners, 8.4mm ID, 16mm OD.",
        "category": "Fasteners",
        "unit_of_measure": "each",
        "unit_price": 0.04,
        "attributes": {
            "fits_thread": "M8",
            "material": "zinc-plated steel",
            "inner_diameter_mm": 8.4,
            "outer_diameter_mm": 16.0,
            "type": "flat washer",
        },
        "search_terms": "m8 washer flat washers zinc plated steel metric",
    },
    {
        "sku": "ATL-1320",
        "name": "M8 Stainless Split Lock Washer",
        "description": "304 stainless steel split lock washer for M8 fasteners.",
        "category": "Fasteners",
        "unit_of_measure": "each",
        "unit_price": 0.11,
        "attributes": {
            "fits_thread": "M8",
            "material": "304 stainless steel",
            "type": "split lock washer",
        },
        "search_terms": "m8 washer lock washer split stainless ss metric",
    },
    {
        "sku": "ATL-1410",
        "name": "M8 Stainless Hex Nut",
        "description": "304 stainless steel hex nut, M8-1.25 thread.",
        "category": "Fasteners",
        "unit_of_measure": "each",
        "unit_price": 0.14,
        "attributes": {
            "thread_size": "M8-1.25",
            "material": "304 stainless steel",
            "type": "hex nut",
        },
        "search_terms": "m8 nut hex nut stainless ss metric",
    },
    {
        "sku": "ATL-1420",
        "name": "M8 Stainless Nylon-Insert Lock Nut",
        "description": "304 stainless steel nylon-insert lock nut, M8-1.25 thread.",
        "category": "Fasteners",
        "unit_of_measure": "each",
        "unit_price": 0.23,
        "attributes": {
            "thread_size": "M8-1.25",
            "material": "304 stainless steel",
            "type": "nylon-insert lock nut",
        },
        "search_terms": "m8 nut lock nut nyloc nylon insert stainless ss metric",
    },
    # --- Safety: gloves (three chemical-resistant materials -> ambiguity) --
    {
        "sku": "ATL-2110",
        "name": "Nitrile Chemical-Resistant Gloves, 15 mil",
        "description": "Unlined 15 mil nitrile gloves with a 13-inch cuff. Good general solvent and oil resistance.",
        "category": "Safety",
        "unit_of_measure": "pair",
        "unit_price": 4.85,
        "attributes": {
            "material": "nitrile",
            "thickness_mil": 15,
            "cuff_length_in": 13,
            "protection": "chemical resistant",
            "sizes": ["M", "L", "XL"],
        },
        "search_terms": "gloves chemical resistant nitrile solvent oil hand protection ppe",
    },
    {
        "sku": "ATL-2120",
        "name": "Neoprene Chemical-Resistant Gloves, 18 mil",
        "description": "Flock-lined 18 mil neoprene gloves with a 13-inch cuff. Strong acid and caustic resistance.",
        "category": "Safety",
        "unit_of_measure": "pair",
        "unit_price": 6.40,
        "attributes": {
            "material": "neoprene",
            "thickness_mil": 18,
            "cuff_length_in": 13,
            "protection": "chemical resistant",
            "sizes": ["M", "L", "XL"],
        },
        "search_terms": "gloves chemical resistant neoprene acid caustic hand protection ppe",
    },
    {
        "sku": "ATL-2130",
        "name": "Butyl Chemical-Resistant Gloves, 25 mil",
        "description": "Unsupported 25 mil butyl gloves with a 14-inch cuff. Highest resistance to ketones and esters.",
        "category": "Safety",
        "unit_of_measure": "pair",
        "unit_price": 18.75,
        "attributes": {
            "material": "butyl",
            "thickness_mil": 25,
            "cuff_length_in": 14,
            "protection": "chemical resistant",
            "sizes": ["L", "XL"],
        },
        "search_terms": "gloves chemical resistant butyl ketone ester hand protection ppe",
    },
    {
        "sku": "ATL-2210",
        "name": "Cut-Resistant Work Gloves, ANSI A4",
        "description": "HPPE-blend shell with polyurethane palm coating. ANSI/ISEA cut level A4.",
        "category": "Safety",
        "unit_of_measure": "pair",
        "unit_price": 7.20,
        "attributes": {
            "material": "HPPE blend",
            "cut_level": "ANSI A4",
            "coating": "polyurethane palm",
            "sizes": ["S", "M", "L", "XL"],
        },
        "search_terms": "gloves cut resistant work gloves hand protection ppe a4",
    },
    {
        "sku": "ATL-2310",
        "name": "Clear Anti-Fog Safety Glasses",
        "description": "Polycarbonate safety glasses with anti-fog coating. ANSI Z87.1 rated.",
        "category": "Safety",
        "unit_of_measure": "each",
        "unit_price": 3.95,
        "attributes": {
            "lens": "clear polycarbonate",
            "coating": "anti-fog",
            "rating": "ANSI Z87.1",
        },
        "search_terms": "safety glasses eye protection spectacles z87 anti fog ppe",
    },
    {
        "sku": "ATL-2410",
        "name": "Foam Earplugs, NRR 32, Corded",
        "description": "Corded polyurethane foam earplugs, noise reduction rating 32 dB. 200 pairs per box.",
        "category": "Safety",
        "unit_of_measure": "box",
        "unit_price": 32.50,
        "attributes": {"nrr_db": 32, "corded": True, "pairs_per_box": 200},
        "search_terms": "earplugs hearing protection ear plugs noise nrr ppe",
    },
    # --- Maintenance -----------------------------------------------------
    {
        "sku": "ATL-3204",
        "name": "6204-2RS Sealed Ball Bearing",
        "description": "Deep-groove ball bearing, 20mm bore, 47mm OD, 14mm width, double rubber seal.",
        "category": "Maintenance",
        "unit_of_measure": "each",
        "unit_price": 8.90,
        "attributes": {"bore_mm": 20, "outer_diameter_mm": 47, "width_mm": 14, "seal": "2RS double rubber"},
        "search_terms": "bearing ball bearing sealed 6204 deep groove 2rs",
    },
    {
        "sku": "ATL-3205",
        "name": "6205-2RS Sealed Ball Bearing",
        "description": "Deep-groove ball bearing, 25mm bore, 52mm OD, 15mm width, double rubber seal.",
        "category": "Maintenance",
        "unit_of_measure": "each",
        "unit_price": 10.40,
        "attributes": {"bore_mm": 25, "outer_diameter_mm": 52, "width_mm": 15, "seal": "2RS double rubber"},
        "search_terms": "bearing ball bearing sealed 6205 deep groove 2rs",
    },
    {
        "sku": "ATL-3206",
        "name": "6206-2RS Sealed Ball Bearing",
        "description": "Deep-groove ball bearing, 30mm bore, 62mm OD, 16mm width, double rubber seal.",
        "category": "Maintenance",
        "unit_of_measure": "each",
        "unit_price": 12.75,
        "attributes": {"bore_mm": 30, "outer_diameter_mm": 62, "width_mm": 16, "seal": "2RS double rubber"},
        "search_terms": "bearing ball bearing sealed 6206 deep groove 2rs",
    },
    {
        "sku": "ATL-3310",
        "name": "Lithium Complex Grease Cartridge, 14 oz",
        "description": "NLGI 2 lithium complex grease in a 14 oz cartridge for standard grease guns.",
        "category": "Maintenance",
        "unit_of_measure": "cartridge",
        "unit_price": 6.15,
        "attributes": {"grade": "NLGI 2", "type": "lithium complex", "size_oz": 14},
        "search_terms": "grease lithium cartridge lubricant grease gun nlgi",
    },
    {
        "sku": "ATL-3320",
        "name": "Penetrating Lubricant Spray, 11 oz",
        "description": "Aerosol penetrating oil for freeing seized fasteners. 11 oz can.",
        "category": "Maintenance",
        "unit_of_measure": "can",
        "unit_price": 7.80,
        "attributes": {"size_oz": 11, "form": "aerosol"},
        "search_terms": "penetrating oil lubricant spray aerosol rust seized loosener",
    },
    {
        "sku": "ATL-3410",
        "name": "Blue Medium-Strength Threadlocker, 50 mL",
        "description": "Medium-strength anaerobic threadlocker for fasteners up to 25mm. 50 mL bottle.",
        "category": "Maintenance",
        "unit_of_measure": "bottle",
        "unit_price": 14.30,
        "attributes": {"strength": "medium", "colour": "blue", "size_ml": 50},
        "search_terms": "threadlocker thread locker loctite blue medium anaerobic adhesive",
    },
    # --- Electrical ------------------------------------------------------
    {
        "sku": "ATL-4014",
        "name": "14 AWG Primary Wire, Black, 100 ft",
        "description": "Stranded copper primary wire, 14 AWG, PVC insulation, 100 ft spool.",
        "category": "Electrical",
        "unit_of_measure": "spool",
        "unit_price": 21.50,
        "attributes": {"gauge_awg": 14, "colour": "black", "length_ft": 100, "conductor": "stranded copper"},
        "search_terms": "wire primary wire 14 awg gauge copper stranded spool electrical",
    },
    {
        "sku": "ATL-4012",
        "name": "12 AWG Primary Wire, Black, 100 ft",
        "description": "Stranded copper primary wire, 12 AWG, PVC insulation, 100 ft spool.",
        "category": "Electrical",
        "unit_of_measure": "spool",
        "unit_price": 29.90,
        "attributes": {"gauge_awg": 12, "colour": "black", "length_ft": 100, "conductor": "stranded copper"},
        "search_terms": "wire primary wire 12 awg gauge copper stranded spool electrical",
    },
    {
        "sku": "ATL-4110",
        "name": "8-inch Nylon Cable Ties, Black, 100 pack",
        "description": "UV-resistant nylon 6/6 cable ties, 8 inch length, 50 lb tensile strength. 100 per pack.",
        "category": "Electrical",
        "unit_of_measure": "pack",
        "unit_price": 9.25,
        "attributes": {"length_in": 8, "tensile_lb": 50, "material": "nylon 6/6", "pack_qty": 100},
        "search_terms": "cable ties zip ties nylon wire ties tie wraps",
    },
    {
        "sku": "ATL-4210",
        "name": "Heat-Shrink Tubing Assortment, 3:1 Adhesive-Lined",
        "description": "Adhesive-lined 3:1 heat-shrink tubing assortment, six diameters, 160 pieces.",
        "category": "Electrical",
        "unit_of_measure": "kit",
        "unit_price": 26.40,
        "attributes": {"ratio": "3:1", "lining": "adhesive", "pieces": 160},
        "search_terms": "heat shrink tubing shrink wrap adhesive lined assortment electrical",
    },
    # --- Shop supplies / packaging ---------------------------------------
    {
        "sku": "ATL-5110",
        "name": "Blue Shop Towels, 12-roll case",
        "description": "Heavy-duty disposable blue shop towels, 55 sheets per roll, 12 rolls per case.",
        "category": "Shop Supplies",
        "unit_of_measure": "case",
        "unit_price": 41.00,
        "attributes": {"rolls_per_case": 12, "sheets_per_roll": 55},
        "search_terms": "shop towels rags paper towels wipes cleaning",
    },
    {
        "sku": "ATL-5210",
        "name": "2-inch Clear Packing Tape, 36-roll case",
        "description": "2 inch x 110 yd clear acrylic packing tape, 36 rolls per case.",
        "category": "Packaging",
        "unit_of_measure": "case",
        "unit_price": 58.75,
        "attributes": {"width_in": 2, "length_yd": 110, "rolls_per_case": 36},
        "search_terms": "packing tape packaging tape clear carton sealing tape",
    },
    {
        "sku": "ATL-5310",
        "name": "12 x 12 x 8 inch Corrugated Shipping Box, 25 pack",
        "description": "Single-wall corrugated shipping boxes, 32 ECT, 25 per bundle.",
        "category": "Packaging",
        "unit_of_measure": "bundle",
        "unit_price": 34.20,
        "attributes": {"dimensions_in": "12x12x8", "ect": 32, "qty_per_bundle": 25},
        "search_terms": "boxes corrugated shipping box cartons packaging",
    },
]

# ---------------------------------------------------------------------------
# Inventory: sku -> (on_hand, allocated, restock_in_days)
# `restock_in_days` is relative so a reseeded demo always looks current.
# ---------------------------------------------------------------------------

INVENTORY: dict[str, tuple[int, int, int | None]] = {
    "ATL-1020": (4200, 350, None),
    "ATL-1030": (2850, 1100, None),
    "ATL-1040": (1900, 240, None),
    "ATL-1050": (760, 0, None),
    "ATL-1031": (6400, 500, None),
    "ATL-1130": (1450, 120, None),
    "ATL-1210": (2300, 0, None),
    "ATL-1310": (12400, 900, None),
    "ATL-1311": (18600, 1200, None),
    "ATL-1320": (5400, 0, None),
    "ATL-1410": (7800, 400, None),
    "ATL-1420": (3300, 150, None),
    # Deliberately short: an order for 300 pairs cannot be fully promised.
    "ATL-2110": (180, 40, 12),
    "ATL-2120": (640, 60, None),
    "ATL-2130": (95, 0, 21),
    "ATL-2210": (1250, 80, None),
    "ATL-2310": (2600, 150, None),
    "ATL-2410": (410, 20, None),
    "ATL-3204": (320, 45, None),
    "ATL-3205": (275, 100, None),
    # Backordered entirely -> exercises the zero-availability path.
    "ATL-3206": (0, 0, 9),
    "ATL-3310": (890, 120, None),
    "ATL-3320": (540, 30, None),
    "ATL-3410": (260, 10, None),
    "ATL-4014": (185, 25, None),
    "ATL-4012": (140, 40, None),
    "ATL-4110": (720, 60, None),
    "ATL-4210": (95, 5, 14),
    "ATL-5110": (240, 30, None),
    "ATL-5210": (310, 45, None),
    "ATL-5310": (150, 20, None),
}

# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

CUSTOMERS: list[dict] = [
    {
        "account_number": "NM-4471",
        "company_name": "Northstar Manufacturing",
        "contact_name": "Ahmed Hassan",
        "email": "ahmed.hassan@northstar-mfg.example",
        "phone": "+1-614-555-0142",
        "status": "active",
    },
    {
        "account_number": "AF-2280",
        "company_name": "Apex Fabrication",
        "contact_name": "Rachel Kim",
        "email": "rachel.kim@apexfab.example",
        "phone": "+1-216-555-0119",
        "status": "active",
    },
    {
        "account_number": "RP-6635",
        "company_name": "Riverside Packaging",
        "contact_name": "Daniel Ortega",
        "email": "daniel.ortega@riversidepack.example",
        "phone": "+1-513-555-0177",
        "status": "active",
    },
    {
        "account_number": "SA-1902",
        "company_name": "Summit Automation",
        "contact_name": "Priya Raman",
        "email": "priya.raman@summitauto.example",
        "phone": "+1-937-555-0155",
        "status": "active",
    },
    {
        "account_number": "HM-3318",
        "company_name": "Harbor Machine Works",
        "contact_name": "Tomas Vail",
        "email": "tomas.vail@harbormachine.example",
        "phone": "+1-440-555-0163",
        "status": "active",
    },
    {
        "account_number": "CI-8804",
        "company_name": "Cedar Industrial Services",
        "contact_name": "Grace Whitfield",
        "email": "grace.whitfield@cedarindustrial.example",
        "phone": "+1-419-555-0128",
        # On credit hold -> the agent has a reason to decline an RFQ politely.
        "status": "on_hold",
    },
]


# ---------------------------------------------------------------------------
# Purchase orders
#
# Dates are expressed as offsets in days from the moment the database is
# seeded, so a freshly reset demo always has a shipment landing "this Friday"
# rather than a date that quietly went stale months ago.
#
# `ship_on_next_weekday: 4` means "the next upcoming Friday" (Mon=0).
# ---------------------------------------------------------------------------

ORDERS: list[dict] = [
    {
        # ---- Flagship demo order -------------------------------------
        # Line 2 is the one the caller reduces from 500 to 200.
        "po_number": "1847",
        "account_number": "NM-4471",
        "status": "processing",
        "customer_reference": "NS-REQ-88213",
        "created_days_ago": 6,
        "lines": [
            {"sku": "ATL-1030", "quantity": 600, "status": "allocated", "shipment": "A"},
            {"sku": "ATL-1310", "quantity": 500, "status": "open"},
            {"sku": "ATL-3310", "quantity": 24, "status": "open"},
        ],
        "shipments": [
            {
                "ref": "A",
                "carrier": "UPS Ground",
                "status": "pending",
                "ship_on_next_weekday": 4,  # this coming Friday
                "delivery_offset_days": 3,  # three days after it ships
                "tracking_number": None,
            }
        ],
    },
    {
        # ---- Already shipped: every modification must be refused -----
        "po_number": "1260",
        "account_number": "AF-2280",
        "status": "shipped",
        "customer_reference": "APX-PO-4410",
        "created_days_ago": 21,
        "lines": [
            {"sku": "ATL-3204", "quantity": 40, "status": "shipped", "shipment": "A"},
            {"sku": "ATL-3310", "quantity": 12, "status": "shipped", "shipment": "A"},
        ],
        "shipments": [
            {
                "ref": "A",
                "carrier": "FedEx Ground",
                "status": "in_transit",
                "ship_offset_days": -3,
                "delivery_offset_days": 1,
                "tracking_number": "ATLZ4471902883",
            }
        ],
    },
    {
        # ---- Two lines from the same ambiguous family ----------------
        # "the M8 screws on 1932" matches both line 1 and line 2, so the
        # agent has to ask which one before it can act.
        "po_number": "1932",
        "account_number": "RP-6635",
        "status": "confirmed",
        "customer_reference": "RSP-2291",
        "created_days_ago": 3,
        "lines": [
            {"sku": "ATL-1020", "quantity": 250, "status": "open"},
            {"sku": "ATL-1040", "quantity": 250, "status": "open"},
            {"sku": "ATL-2120", "quantity": 30, "status": "open"},
        ],
        "shipments": [],
    },
    {
        # ---- Cancelled ------------------------------------------------
        "po_number": "2001",
        "account_number": "SA-1902",
        "status": "cancelled",
        "customer_reference": "SUM-9930",
        "created_days_ago": 14,
        "lines": [
            {"sku": "ATL-4014", "quantity": 10, "status": "cancelled"},
            {"sku": "ATL-4110", "quantity": 6, "status": "cancelled"},
        ],
        "shipments": [],
    },
    {
        # ---- Partially shipped: order editable, line 1 is not ---------
        # This is the case that proves the order-level and line-level rules
        # are genuinely separate checks.
        "po_number": "1905",
        "account_number": "AF-2280",
        "status": "processing",
        "customer_reference": "APX-PO-4478",
        "created_days_ago": 9,
        "lines": [
            {"sku": "ATL-2210", "quantity": 120, "status": "shipped", "shipment": "A"},
            {"sku": "ATL-2310", "quantity": 200, "status": "allocated", "shipment": "B"},
            {"sku": "ATL-5110", "quantity": 8, "status": "open"},
        ],
        "shipments": [
            {
                "ref": "A",
                "carrier": "UPS Ground",
                "status": "in_transit",
                "ship_offset_days": -2,
                "delivery_offset_days": 2,
                "tracking_number": "ATLZ4471885120",
            },
            {
                "ref": "B",
                "carrier": "UPS Ground",
                "status": "pending",
                "ship_offset_days": 4,
                "delivery_offset_days": 3,
                "tracking_number": None,
            },
        ],
    },
    {
        # ---- Second Northstar order: the caller's company alone is not
        # enough to identify an order, so the PO number still matters.
        "po_number": "1890",
        "account_number": "NM-4471",
        "status": "confirmed",
        "customer_reference": "NS-REQ-88540",
        "created_days_ago": 2,
        "lines": [
            {"sku": "ATL-1410", "quantity": 800, "status": "open"},
            {"sku": "ATL-1320", "quantity": 800, "status": "open"},
        ],
        "shipments": [],
    },
    {
        "po_number": "1783",
        "account_number": "HM-3318",
        "status": "shipped",
        "customer_reference": "HMW-1188",
        "created_days_ago": 33,
        "lines": [
            {"sku": "ATL-3205", "quantity": 60, "status": "shipped", "shipment": "A"},
            {"sku": "ATL-3410", "quantity": 15, "status": "shipped", "shipment": "A"},
        ],
        "shipments": [
            {
                "ref": "A",
                "carrier": "FedEx Ground",
                "status": "delivered",
                "ship_offset_days": -28,
                "delivery_offset_days": 3,
                "tracking_number": "ATLZ4471770034",
            }
        ],
    },
    {
        # ---- Draft: fully editable, nothing allocated ----------------
        "po_number": "2014",
        "account_number": "SA-1902",
        "status": "draft",
        "customer_reference": "SUM-10021",
        "created_days_ago": 1,
        "lines": [
            {"sku": "ATL-4012", "quantity": 12, "status": "open"},
            {"sku": "ATL-4210", "quantity": 4, "status": "open"},
        ],
        "shipments": [],
    },
    {
        "po_number": "2036",
        "account_number": "RP-6635",
        "status": "processing",
        "customer_reference": "RSP-2340",
        "created_days_ago": 4,
        "lines": [
            {"sku": "ATL-5210", "quantity": 20, "status": "allocated", "shipment": "A"},
            {"sku": "ATL-5310", "quantity": 40, "status": "open"},
        ],
        "shipments": [
            {
                "ref": "A",
                "carrier": "UPS Ground",
                "status": "pending",
                "ship_offset_days": 2,
                "delivery_offset_days": 2,
                "tracking_number": None,
            }
        ],
    },
    {
        "po_number": "2052",
        "account_number": "HM-3318",
        "status": "confirmed",
        "customer_reference": "HMW-1203",
        "created_days_ago": 1,
        "lines": [
            {"sku": "ATL-1130", "quantity": 400, "status": "open"},
            {"sku": "ATL-2410", "quantity": 10, "status": "open"},
        ],
        "shipments": [],
    },
]

# ---------------------------------------------------------------------------
# Pre-existing RFQs, so the RFQ number sequence does not start from scratch and
# a freshly created RFQ gets a plausible-looking number.
# ---------------------------------------------------------------------------

RFQS: list[dict] = [
    {
        "rfq_number": "RFQ-1025",
        "account_number": "AF-2280",
        "status": "quoted",
        "created_days_ago": 11,
        "source": "email",
        "lines": [{"sku": "ATL-3205", "quantity": 120}],
    },
    {
        "rfq_number": "RFQ-1026",
        "account_number": "HM-3318",
        "status": "pricing",
        "created_days_ago": 5,
        "source": "email",
        "lines": [
            {"sku": "ATL-1050", "quantity": 500},
            {"sku": "ATL-1420", "quantity": 500},
        ],
    },
    {
        "rfq_number": "RFQ-1027",
        "account_number": "RP-6635",
        "status": "submitted",
        "created_days_ago": 1,
        "source": "web",
        "lines": [{"sku": "ATL-5310", "quantity": 200}],
    },
]
