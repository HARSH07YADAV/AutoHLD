"""
generate_large_sample_hld.py — Generates a 25-page comprehensive AUTOSAR HLD document PDF
for testing and demonstrating the AutoHLD analysis platform.

Output:
    demo/sample_docs/AUTOSAR_BMS_Powertrain_HLD_v3.4.pdf

Usage:
    .venv/bin/python demo/generate_large_sample_hld.py
"""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)

OUTPUT_DIR = Path(__file__).parent / "sample_docs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "AUTOSAR_BMS_Powertrain_HLD_v3.4.pdf"


def make_table(data, col_widths=None):
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#F8FAFC')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F8FAFC'), colors.HexColor('#EFF6FF')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
    ]))
    return t


def build_pdf():
    doc = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=2.0 * cm,
        bottomMargin=2.0 * cm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.HexColor('#0F172A'),
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Heading2'],
        fontName='Helvetica',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#2563EB'),
        spaceAfter=14,
    )
    h1 = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=19,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=10,
        spaceAfter=8,
    )
    h2 = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#1E293B'),
        spaceBefore=8,
        spaceAfter=6,
    )
    h3 = ParagraphStyle(
        'Heading3_Custom',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor('#2563EB'),
        spaceBefore=6,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        'Body_Custom',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#334155'),
        spaceAfter=6,
    )
    code_text = ParagraphStyle(
        'Code_Custom',
        parent=styles['Code'],
        fontName='Courier',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0F172A'),
    )

    story = []

    # ── Page 1: Cover Page ──────────────────────────────────────────────────
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph("NextGen EV Powertrain &amp; Battery Management System", title_style))
    story.append(Paragraph("AUTOSAR Classic Platform 4.4 High-Level Software Design (HLD)", subtitle_style))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph("<b>Document Identifier:</b> HLD-BMS-PWR-2026-V3.4", body))
    story.append(Paragraph("<b>Classification:</b> Internal Engineering Use Only · ISO 26262 ASIL-D", body))
    story.append(Paragraph("<b>Vehicle Program:</b> Platform-X High-Voltage Battery Pack (800V Architecture)", body))
    story.append(Paragraph("<b>Target ECU:</b> BMS Main Controller (Infineon AURIX TC397x Multi-Core MCU)", body))
    story.append(Paragraph("<b>AUTOSAR Release:</b> Classic Platform Release 4.4.0", body))
    story.append(Paragraph("<b>Document Version:</b> 3.4.0 (Approved for Baseline Release)", body))
    story.append(Paragraph("<b>Release Date:</b> October 2026", body))
    story.append(PageBreak())

    # ── Page 2: Document Revision History & Approvals ──────────────────────
    story.append(Paragraph("Document Revision History &amp; Approvals", h1))
    story.append(Paragraph("This register tracks engineering revisions, baseline releases, and engineering sign-offs in accordance with ASPICE SWE.1 and ISO 26262 functional safety processes.", body))
    story.append(Spacer(1, 0.4 * cm))

    rev_data = [
        ["Rev", "Date", "Author", "Engineering Scope & Changes", "Status"],
        ["1.0", "2025-04-12", "H. Schmidt", "Initial architectural baseline and component decomposition", "Approved"],
        ["2.0", "2025-10-18", "M. Tanaka", "Added ThermalManagement SWC and cooling loop controls", "Approved"],
        ["2.3", "2026-03-05", "D. Miller", "High-voltage contactor state machine and precharge logic", "Approved"],
        ["3.0", "2026-06-20", "E. Vance", "Integrated CCS/NACS ChargingControl and ISO 15118 stack", "Approved"],
        ["3.4", "2026-10-15", "A. Kowalski", "Updated port matrix, cell balancing, and safety watchdog SWC", "Released"],
    ]
    story.append(make_table(rev_data, [30, 60, 80, 240, 60]))
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph("Engineering Approvals Sign-off", h2))
    appr_data = [
        ["Role", "Name", "Department", "Signature Date"],
        ["Lead Systems Architect", "Dr. Marcus Vance", "E/E Architecture Group", "2026-10-16"],
        ["Functional Safety Manager", "Elena Rostova", "Automotive Safety & Compliance", "2026-10-17"],
        ["Software Project Lead", "Rajesh Nair", "Powertrain Software Delivery", "2026-10-18"],
    ]
    story.append(make_table(appr_data, [130, 110, 140, 90]))
    story.append(PageBreak())

    # ── Page 3: Table of Contents ───────────────────────────────────────────
    story.append(Paragraph("Table of Contents", h1))
    story.append(Spacer(1, 0.3 * cm))
    toc = [
        "1. Executive Summary & Vehicle E/E Architecture Context",
        "2. Functional Safety Concept & ISO 26262 ASIL Decomposition",
        "3. Hardware Platform & Microcontroller Mapping (AURIX TC397x)",
        "4. AUTOSAR Layered Architecture & RTE Configuration Overview",
        "5. BatteryManagement SWC Specification (Cell Monitoring & SOC)",
        "6. ThermalManagement SWC Specification (Cooling & Heating Loops)",
        "7. PowerControl & High-Voltage Contactor Management SWC",
        "8. StateOfHealth & CellBalancing SWC Specification",
        "9. ChargingControl SWC Specification (AC / DC Fast Charging)",
        "10. InverterInterface & Traction Drive Coordination SWC",
        "11. VehicleSafetySupervisor & Watchdog SWC (ASIL-D Core Plausibility)",
        "12. Diagnostics & Fault Management SWC (DEM, DCM, ISO 14229 UDS)",
        "13. Port and Interface Definition Matrix (Comprehensive Catalogue)",
        "14. Data Dictionary & Global Signal Catalogue",
        "15. Runnable Entities & OS Task Scheduling Allocation",
        "16. In-Vehicle Communication Matrix (CAN FD & Automotive Ethernet)",
        "17. Non-Volatile Memory (NvM) Block Layout & Persistence",
        "18. End-to-End (E2E) Communication Protection Concept",
        "19. Vehicle Mode Management & Power State Machine",
        "20. Cross-Component Sequences & Interaction Flows",
        "21. Intentional Architectural Inconsistencies & Known Issues Register",
        "22. Integration Guidelines & RTE Generation Directives",
        "23. Verification & Validation Acceptance Criteria (MIL, SIL, HIL)",
        "24. Abbreviations, Symbols & Glossary of Automotive Terms",
    ]
    for item in toc:
        story.append(Paragraph(item, body))
    story.append(PageBreak())

    # ── Page 4: Section 1 — Executive Summary & Vehicle Architecture ───────
    story.append(Paragraph("1. Executive Summary &amp; Vehicle E/E Architecture Context", h1))
    story.append(Paragraph(
        "This High-Level Design document establishes the formal software architecture for the Battery "
        "Management System (BMS) and Powertrain Coordination Controller within the Platform-X 800V "
        "electric vehicle platform. The system operates in a distributed automotive environment connecting "
        "through dual CAN FD buses and an Automotive Ethernet backbone.", body))
    story.append(Paragraph(
        "The primary mission of the BMS software is to maintain battery pack safety under all operational "
        "conditions, accurately estimate State of Charge (SOC) and State of Health (SOH), coordinate thermal "
        "cooling and heating circuits, control high-voltage contactor precharge and isolation, and support "
        "high-power DC fast charging up to 350 kW.", body))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Key Architectural Characteristics:", h2))
    story.append(Paragraph("• <b>Layered AUTOSAR Architecture:</b> Full separation between Application Software Components (ASW), Runtime Environment (RTE), and Basic Software (BSW).", body))
    story.append(Paragraph("• <b>Dual Microcontroller Cores:</b> Core 0 runs safety-critical voltage monitoring and precharge tasks; Core 1 executes thermal control and state estimation.", body))
    story.append(Paragraph("• <b>ISO 26262 ASIL-D Compliance:</b> Redundant voltage and current measurement plausibility with hardware-enforced emergency shut-off paths.", body))
    story.append(Paragraph("• <b>Real-time Determinism:</b> Cyclic task execution with 1 ms, 5 ms, 10 ms, and 100 ms periodicities scheduled by the AUTOSAR OSEK/VDX OS.", body))
    story.append(PageBreak())

    # ── Page 5: Section 2 — Functional Safety & ASIL Decomposition ──────────
    story.append(Paragraph("2. Functional Safety Concept &amp; ISO 26262 ASIL Decomposition", h1))
    story.append(Paragraph(
        "In accordance with ISO 26262:2018 Road Vehicles — Functional Safety, a Hazard Analysis and "
        "Risk Assessment (HARA) identified critical top-level vehicle hazards relating to high-voltage "
        "battery failure modes. The following safety goals are assigned to the software architecture:", body))
    story.append(Spacer(1, 0.3 * cm))

    safety_data = [
        ["Safety Goal ID", "Safety Goal Description", "ASIL", "FTTI", "Allocated SWC"],
        ["SG-01", "Prevent battery cell overcharge leading to thermal runaway", "ASIL-D", "50 ms", "BatteryManagement"],
        ["SG-02", "Prevent unintended closing of main high-voltage contactors", "ASIL-D", "20 ms", "PowerControl"],
        ["SG-03", "Ensure high-voltage bus discharge upon crash detection", "ASIL-D", "100 ms", "VehicleSafetySupervisor"],
        ["SG-04", "Prevent pack overheating during extreme driving / DC fast charge", "ASIL-B", "500 ms", "ThermalManagement"],
        ["SG-05", "Detect high-voltage isolation loss to vehicle chassis ground", "ASIL-C", "200 ms", "PowerControl"],
    ]
    story.append(make_table(safety_data, [60, 160, 45, 50, 155]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Fault Tolerant Time Interval (FTTI) Budgeting", h2))
    story.append(Paragraph(
        "For SG-01, the overall FTTI is 50 ms. The software detection budget is allocated 20 ms, leaving "
        "30 ms for hardware actuator response (opening solid-state pyrofuse and main pack contactors). "
        "The runnable Runnable_BattMonitor executes every 10 ms to guarantee double-sampling verification within the allotted budget.", body))
    story.append(PageBreak())

    # ── Page 6: Section 3 — Hardware Platform & AURIX TC397x Mapping ───────
    story.append(Paragraph("3. Hardware Platform &amp; Microcontroller Mapping", h1))
    story.append(Paragraph(
        "The target ECU hardware incorporates an Infineon AURIX TC397x TriCore microcontroller featuring "
        "6 cores clocked at 300 MHz, with 16 MB embedded flash and 2.9 MB SRAM. Lockstep cores (Core 0 and Core 1) "
        "provide hardware safety redundancy for ASIL-D computation.", body))
    story.append(Spacer(1, 0.3 * cm))

    hw_table = [
        ["Core ID", "Architecture Role", "Software Allocation", "Safety Level"],
        ["Core 0 (Lockstep)", "Master Safety Controller", "BatteryManagement, VehicleSafetySupervisor", "ASIL-D"],
        ["Core 1 (Lockstep)", "Actuation & Power Control", "PowerControl, InverterInterface", "ASIL-D"],
        ["Core 2", "Thermal & Auxiliary Processing", "ThermalManagement, CellBalancing", "ASIL-B"],
        ["Core 3", "Charging & Communications", "ChargingControl, COM Stack, Ethernet", "ASIL-B / QM"],
        ["Core 4", "Diagnostics & Telemetry", "Diagnostics SWC, DEM, DCM, UDS Stack", "QM"],
        ["Core 5", "Reserved / System Monitor", "OS Task Timing Watchdog, Memory BIST", "ASIL-D"],
    ]
    story.append(make_table(hw_table, [85, 115, 185, 85]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Hardware Interfaces &amp; Peripherals", h2))
    story.append(Paragraph("• <b>Dual IsoSPI Channels:</b> High-speed isolated serial links connecting 12 daisy-chained Battery Cell Monitoring ICs (ADBMS6815).", body))
    story.append(Paragraph("• <b>CAN FD Controller 0:</b> Powertrain Backbone Bus (500 kbps arbitration / 2.0 Mbps data phase).", body))
    story.append(Paragraph("• <b>Automotive Ethernet (100BASE-T1):</b> Diagnostics, flash reprogramming, and vehicle cloud telemetry.", body))
    story.append(PageBreak())

    # ── Page 7: Section 4 — AUTOSAR Layered Architecture & RTE ──────────────
    story.append(Paragraph("4. AUTOSAR Layered Architecture &amp; RTE Overview", h1))
    story.append(Paragraph(
        "The software architecture strictly adheres to AUTOSAR Classic Platform Release 4.4.0. The application "
        "layer comprises 8 Atomic Software Components (AtomicSWC) interacting exclusively through the AUTOSAR "
        "Runtime Environment (RTE). Direct cross-component memory sharing or bypass calls are strictly prohibited.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("AUTOSAR Architectural Layers:", h2))
    story.append(Paragraph("1. <b>Application Software Layer (ASW):</b> Encapsulates automotive domain algorithms including state-of-charge calculation, contactor state sequences, and temperature regulation.", body))
    story.append(Paragraph("2. <b>Runtime Environment (RTE):</b> Provides standardized communication infrastructure via Sender-Receiver (S/R) and Client-Server (C/S) paradigms.", body))
    story.append(Paragraph("3. <b>Basic Software Layer (BSW):</b> Supplies system services (OS, EcuM, BswM), memory abstraction (NvM, MemIf, Fee), and communication drivers (CanIf, Com, PduR).", body))
    story.append(Paragraph("4. <b>Microcontroller Abstraction Layer (MCAL):</b> Low-level hardware drivers (Gpt, Spi, Dio, Adc, Can) interfacing with AURIX silicon.", body))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Communication Paradigms Used in this Architecture:", h3))
    story.append(Paragraph("• <b>Sender-Receiver (S/R):</b> Used for continuous telemetry data flow (e.g. cell voltages, module temperatures, pack current, and state-of-charge).", body))
    story.append(Paragraph("• <b>Client-Server (C/S):</b> Used for asynchronous service invocations (e.g. requesting contactor opening, triggering NvM write, initiating DTC reset).", body))
    story.append(PageBreak())

    # ── Page 8: Section 5 — BatteryManagement SWC Specification ───────────
    story.append(Paragraph("5. BatteryManagement Software Component Specification", h1))
    story.append(Paragraph("The BatteryManagement SWC represents the foundational component responsible for measuring pack voltages, estimating aggregate State of Charge (SOC), and detecting cell-level anomalies.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Component Attributes:", h2))
    story.append(Paragraph("• <b>Component Type:</b> Application Software Component (AtomicSWC)<br/>"
                           "• <b>Assigned Core:</b> Core 0 (Lockstep)<br/>"
                           "• <b>ASIL Level:</b> ASIL-D<br/>"
                           "• <b>Execution Runnables:</b> Runnable_BattInit (Init), Runnable_BattMonitor (10 ms cyclic), Runnable_BattFault (Event-triggered).", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Port Definitions for BatteryManagement SWC:", h3))

    bms_ports = [
        ["Port Name", "Direction", "Interface", "Description", "Data Type"],
        ["BattVoltage_Prov", "P-Port", "BattVoltage_If", "Provides individual and pack voltage", "float32[96]"],
        ["BattSOC_Prov", "P-Port", "BattSOC_If", "Provides estimated State of Charge", "float32"],
        ["BattCurrent_Prov", "P-Port", "BattCurrent_If", "Provides calibrated shunt pack current", "float32"],
        ["BattFault_Prov", "P-Port", "FaultStatus_If", "Provides battery fault status register", "uint32"],
        ["BattTemp_Req", "R-Port", "TempSensor_If", "Requires module temperature readings", "float32[16]"],
        ["CellBalancing_Req", "R-Port", "BalancingCmd_If", "Demands cell passive balancing action", "uint16"],
    ]
    story.append(make_table(bms_ports, [85, 50, 85, 150, 75]))
    story.append(PageBreak())

    # ── Page 9: Section 6 — ThermalManagement SWC Specification ───────────
    story.append(Paragraph("6. ThermalManagement Software Component Specification", h1))
    story.append(Paragraph("The ThermalManagement SWC orchestrates multi-zone liquid cooling, chiller valves, and resistive pack heaters to maintain lithium-ion cell temperatures between 20°C and 35°C.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Component Attributes:", h2))
    story.append(Paragraph("• <b>Component Type:</b> Sensor-Actuator Software Component<br/>"
                           "• <b>Assigned Core:</b> Core 2<br/>"
                           "• <b>ASIL Level:</b> ASIL-B<br/>"
                           "• <b>Execution Runnables:</b> Runnable_ThermalInit (Init), Runnable_ThermalControl (50 ms cyclic).", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Port Definitions for ThermalManagement SWC:", h3))

    therm_ports = [
        ["Port Name", "Direction", "Interface", "Description", "Data Type"],
        ["CoolingCmd_Prov", "P-Port", "CoolingCmd_If", "Outputs variable cooling pump/fan command", "uint8 (0-100%)"],
        ["HeaterCmd_Prov", "P-Port", "HeaterCmd_If", "Demands PTC coolant heater power level", "uint16 (Watts)"],
        ["TempSensor_Prov", "P-Port", "TempSensor_If", "Publishes validated thermistor values", "float32[16]"],
        ["BattSOC_Req", "R-Port", "BattSOC_If", "Requires SOC for thermal throttling limits", "float32"],
        ["BattFault_Req", "R-Port", "FaultStatus_If", "Requires pack fault state to trigger E-Cool", "uint32"],
        ["AmbientTemp_Req", "R-Port", "VehicleEnv_If", "Requires vehicle external temperature", "float32"],
    ]
    story.append(make_table(therm_ports, [85, 50, 85, 150, 75]))
    story.append(PageBreak())

    # ── Page 10: Section 7 — PowerControl & Contactor Management SWC ───────
    story.append(Paragraph("7. PowerControl &amp; High-Voltage Contactor Management SWC", h1))
    story.append(Paragraph(
        "The PowerControl SWC governs high-voltage contactor opening, precharge resistor timing, and emergency "
        "isolation. It enforces strict timing guards to avoid contactor welding and catastrophic DC bus arcing.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Contactor State Machine Transitions:", h2))
    story.append(Paragraph("1. <b>OPEN:</b> Main positive, main negative, and precharge contactors are de-energized.", body))
    story.append(Paragraph("2. <b>PRECHARGE:</b> Negative contactor closes; precharge contactor engages for 250 ms until inverter DC link reaches 95% of pack voltage.", body))
    story.append(Paragraph("3. <b>CLOSED:</b> Main positive contactor closes; precharge contactor opens. High-voltage path is fully energized.", body))
    story.append(Paragraph("4. <b>FAULT_TRIP:</b> Instantaneous contactor drop (< 15 ms) upon ASIL-D fault flag.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Port Definitions for PowerControl SWC:", h3))

    pwr_ports = [
        ["Port Name", "Direction", "Interface", "Description", "Data Type"],
        ["RelayCmd_Prov", "P-Port", "RelayCmd_If", "Commands main contactor driver relays", "uint8 (bitmap)"],
        ["PrechargeStatus_Prov", "P-Port", "Precharge_If", "Reports DC bus precharge completion", "boolean"],
        ["BattVoltage_Req", "R-Port", "BattVoltage_If", "Requires pack voltage to verify precharge", "float32[96]"],
        ["BattSOC_Req", "R-Port", "BattSOC_If", "Requires SOC to prevent under-voltage load", "float32"],
        ["BattFault_Prov", "P-Port", "FaultStatus_If", "NOTE: Flagged inconsistency - should be R-Port", "uint32"],
        ["EStop_Req", "R-Port", "SafetyTrip_If", "Direct hardware safety trip trigger", "boolean"],
    ]
    story.append(make_table(pwr_ports, [95, 50, 85, 140, 75]))
    story.append(PageBreak())

    # ── Page 11: Section 8 — StateOfHealth & CellBalancing SWC ─────────────
    story.append(Paragraph("8. StateOfHealth &amp; CellBalancing SWC Specification", h1))
    story.append(Paragraph("The StateOfHealth and CellBalancing SWC executes internal resistance tracking, capacity fade degradation modeling, and autonomous passive cell balancing across cell strings.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Algorithmic Methodology:", h2))
    story.append(Paragraph("• <b>Dual Extended Kalman Filter (DEKF):</b> Concurrently estimates cell internal state and remaining amp-hour capacity over lifecycle aging.", body))
    story.append(Paragraph("• <b>Passive Bleed Balancing:</b> Balances cells displaying > 15 mV delta during vehicle rest/charging states using 100 ohm bypass resistors.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Port Definitions for CellBalancing SWC:", h3))

    bal_ports = [
        ["Port Name", "Direction", "Interface", "Description", "Data Type"],
        ["SOH_Metrics_Prov", "P-Port", "SOH_Data_If", "Provides State of Health percentage and IR", "float32"],
        ["BalancingCmd_Prov", "P-Port", "BalancingCmd_If", "Controls individual cell bypass switches", "uint32[3]"],
        ["BattVoltage_Req", "R-Port", "BattVoltage_If", "Requires individual cell voltage values", "float32[96]"],
        ["BattCurrent_Req", "R-Port", "BattCurrent_If", "Requires historical integral current (Ah)", "float32"],
        ["TempSensor_Req", "R-Port", "TempSensor_If", "Requires thermal gradient across modules", "float32[16]"],
    ]
    story.append(make_table(bal_ports, [85, 50, 85, 150, 75]))
    story.append(PageBreak())

    # ── Page 12: Section 9 — ChargingControl SWC Specification ─────────────
    story.append(Paragraph("9. ChargingControl SWC Specification (AC &amp; DC Fast Charge)", h1))
    story.append(Paragraph("The ChargingControl SWC coordinates vehicle EVSE communication, charge current limits, pilot signal state monitoring, and digital handshake protocols in accordance with ISO 15118 and DIN 70121.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Charging Modes Supported:", h2))
    story.append(Paragraph("• <b>AC Level 2 (Type 2 / J1772):</b> On-board charger up to 22 kW three-phase with automated lock actuator control.", body))
    story.append(Paragraph("• <b>DC Fast Charging (CCS2 / NACS):</b> Off-board charging up to 800V / 500A (350 kW) with continuous temperature monitoring.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Port Definitions for ChargingControl SWC:", h3))

    chg_ports = [
        ["Port Name", "Direction", "Interface", "Description", "Data Type"],
        ["ChargeTarget_Prov", "P-Port", "ChargeTarget_If", "Publishes allowable EVSE voltage & current", "uint16[2]"],
        ["InletLock_Prov", "P-Port", "LockActuator_If", "Controls charging flap/lock solenoid", "uint8"],
        ["BattSOC_Req", "R-Port", "BattSOC_If", "Requires pack SOC to apply charging taper", "float32"],
        ["TempSensor_Req", "R-Port", "TempSensor_If", "Monitors inlet and cell temperatures", "float32[16]"],
        ["EVSE_Comm_Req", "R-Port", "ISO15118_If", "Receives EVSE status via HomePlug GreenPHY", "uint8[64]"],
    ]
    story.append(make_table(chg_ports, [85, 50, 85, 150, 75]))
    story.append(PageBreak())

    # ── Page 13: Section 10 — InverterInterface & Traction Coordination ────
    story.append(Paragraph("10. InverterInterface &amp; Traction Drive Coordination SWC", h1))
    story.append(Paragraph("The InverterInterface SWC acts as the high-speed gateway between the Battery Management System and the dual-motor front/rear silicon-carbide (SiC) traction inverters.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Key Responsibilities:", h2))
    story.append(Paragraph("• <b>Dynamic Power Limit Calculation:</b> Computes maximum discharge (acceleration) and regen (braking) power limits updated every 10 ms.", body))
    story.append(Paragraph("• <b>DC Bus Active Discharge:</b> In the event of crash or service shutdown, commands inverters to bleed high-voltage bus below 60V within 2.0 seconds.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Port Definitions for InverterInterface SWC:", h3))

    inv_ports = [
        ["Port Name", "Direction", "Interface", "Description", "Data Type"],
        ["MaxDischarge_Prov", "P-Port", "PowerLimit_If", "Provides maximum allowed discharge kW", "uint16"],
        ["MaxRegen_Prov", "P-Port", "PowerLimit_If", "Provides maximum allowed regenerative kW", "uint16"],
        ["DischargeCmd_Prov", "P-Port", "ActiveBleed_If", "Triggers active inverter discharge gate drive", "boolean"],
        ["InverterStatus_Req", "R-Port", "InvStatus_If", "Monitors inverter DC link voltage & temp", "uint32"],
        ["BattVoltage_Req", "R-Port", "BattVoltage_If", "Requires pack voltage to compute sag limits", "float32[96]"],
    ]
    story.append(make_table(inv_ports, [85, 50, 85, 150, 75]))
    story.append(PageBreak())

    # ── Page 14: Section 11 — VehicleSafetySupervisor SWC (ASIL-D) ─────────
    story.append(Paragraph("11. VehicleSafetySupervisor &amp; Watchdog SWC (ASIL-D)", h1))
    story.append(Paragraph(
        "The VehicleSafetySupervisor SWC runs on the primary lockstep core (Core 0) and performs independent, "
        "diversified plausibility checking of all voltage, current, and temperature inputs to prevent single-point failures.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Safety Mechanisms Implemented:", h2))
    story.append(Paragraph("• <b>E2E Plausibility Check:</b> Compares analog hardware voltage taps with serial IsoSPI digital stream.", body))
    story.append(Paragraph("• <b>Over-Current Hardware Interruption:</b> Coordinates 1200A pyrofuse ignition in case of hard short circuit within 2 ms.", body))
    story.append(Paragraph("• <b>Program Flow Monitoring:</b> Verifies that all ASIL-D cyclic runnables execute in correct sequence without deadline overrun.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Port Definitions for VehicleSafetySupervisor SWC:", h3))

    safety_ports = [
        ["Port Name", "Direction", "Interface", "Description", "Data Type"],
        ["SafetyTrip_Prov", "P-Port", "SafetyTrip_If", "Outputs definitive system-level trip signal", "boolean"],
        ["WatchdogTrigger_Prov", "P-Port", "WdgM_If", "Services external hardware watchdog IC", "uint8"],
        ["BattVoltage_Req", "R-Port", "BattVoltage_If", "Requires raw voltages for cross-validation", "float32[96]"],
        ["BattCurrent_Req", "R-Port", "BattCurrent_If", "Requires raw current for over-current check", "float32"],
        ["CrashSensor_Req", "R-Port", "AirbagSignal_If", "Direct hardwire input from airbag crash ECU", "boolean"],
    ]
    story.append(make_table(safety_ports, [90, 50, 85, 145, 75]))
    story.append(PageBreak())

    # ── Page 15: Section 12 — Diagnostics & Fault Management SWC ───────────
    story.append(Paragraph("12. Diagnostics &amp; Fault Management SWC (DEM / DCM / UDS)", h1))
    story.append(Paragraph("The Diagnostics SWC manages Diagnostic Trouble Codes (DTC), freeze frame snapshot recording, and UDS ISO 14229 client service handling over CAN FD and Ethernet DoIP.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Diagnostic Trouble Codes (DTC) Registry:", h2))

    dtc_table = [
        ["DTC Code", "Hex ID", "Severity", "Description", "Failsafe Action"],
        ["U0100", "0xC10008", "Critical", "Lost Communication with Inverter Gateway", "Open contactors gracefully"],
        ["P0A80", "0x0A8000", "High", "Replace Hybrid/EV Battery Pack Degradation", "Limit power to 50 kW"],
        ["P0AFA", "0x0AFA16", "Critical", "Battery Voltage Sensor Circuit Plausibility", "Prevent driving engagement"],
        ["P0B29", "0x0B2900", "Medium", "Hybrid Battery Pack Cooling Fan Performance", "Derate charge power"],
        ["P0C17", "0x0C1717", "High", "Drive Motor Position Sensor Calibration Error", "Enter Limp-Home mode"],
    ]
    story.append(make_table(dtc_table, [50, 60, 45, 180, 110]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Port Definitions for Diagnostics SWC:", h3))

    diag_ports = [
        ["Port Name", "Direction", "Interface", "Description", "Data Type"],
        ["DTC_Event_Prov", "P-Port", "Dem_Event_If", "Reports fault status flags to DEM stack", "uint32"],
        ["FreezeFrame_Prov", "P-Port", "Dcm_Snapshot_If", "Supplies cell snapshot buffer to DCM", "uint8[128]"],
        ["BattFault_Req", "R-Port", "FaultStatus_If", "Listens for active component faults", "uint32"],
    ]
    story.append(make_table(diag_ports, [85, 50, 85, 150, 75]))
    story.append(PageBreak())

    # ── Page 16: Section 13 — Port and Interface Definition Matrix ─────────
    story.append(Paragraph("13. Port and Interface Definition Matrix", h1))
    story.append(Paragraph("This master matrix consolidates all AUTOSAR PortInterfaces across all 8 software components to verify complete communication closure and interface binding integrity.", body))
    story.append(Spacer(1, 0.3 * cm))

    matrix_data = [
        ["Interface Name", "Interface Type", "Provider Component", "Requirer Component(s)", "Cycle"],
        ["BattVoltage_If", "Sender-Receiver", "BatteryManagement", "PowerControl, Inverter, Safety", "10 ms"],
        ["BattSOC_If", "Sender-Receiver", "BatteryManagement", "PowerControl, Thermal, Charging", "100 ms"],
        ["BattCurrent_If", "Sender-Receiver", "BatteryManagement", "CellBalancing, SafetySupervisor", "5 ms"],
        ["FaultStatus_If", "Sender-Receiver", "BatteryManagement", "Thermal, Diagnostics, PowerControl", "Event"],
        ["TempSensor_If", "Sender-Receiver", "ThermalManagement", "BatteryManagement, CellBalancing", "50 ms"],
        ["CoolingCmd_If", "Sender-Receiver", "ThermalManagement", "Thermal Actuator Drivers", "100 ms"],
        ["RelayCmd_If", "Sender-Receiver", "PowerControl", "MCAL Dio Driver", "10 ms"],
        ["SafetyTrip_If", "Sender-Receiver", "VehicleSafetySupervisor", "PowerControl (Emergency Open)", "1 ms"],
        ["Dem_Event_If", "Client-Server", "Diagnostics", "BSW DEM Service", "Event"],
    ]
    story.append(make_table(matrix_data, [90, 75, 95, 135, 50]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Interface Integrity Rules:", h2))
    story.append(Paragraph("1. Every P-Port must have at least one valid matching R-Port in the composition.", body))
    story.append(Paragraph("2. Data types, arrays lengths, and unit scaling must match precisely between provider and requirer.", body))
    story.append(PageBreak())

    # ── Page 17: Section 14 — Data Dictionary & Global Signal Catalogue ────
    story.append(Paragraph("14. Data Dictionary &amp; Global Signal Catalogue", h1))
    story.append(Paragraph("The Data Dictionary standardizes the naming, base type, physical minimum, maximum, scaling factor, and initial value for all signals exchanged over the RTE.", body))
    story.append(Spacer(1, 0.3 * cm))

    dict_data = [
        ["Signal Name", "Data Type", "Min", "Max", "Resolution", "Unit", "Init Val"],
        ["CellVoltage_mV", "uint16[96]", "1500", "4500", "1.0", "mV", "3700"],
        ["PackCurrent_A", "float32", "-800.0", "800.0", "0.01", "A", "0.0"],
        ["PackSOC_Pct", "float32", "0.0", "100.0", "0.1", "%", "50.0"],
        ["MaxTemp_DegC", "float32", "-40.0", "125.0", "0.25", "°C", "25.0"],
        ["ContactorState", "uint8", "0", "4", "1", "Enum", "0 (Open)"],
        ["Isolation_kOhm", "uint16", "0", "65535", "1.0", "kΩ", "10000"],
        ["PyrofuseState", "boolean", "0", "1", "1", "Flag", "0 (Intact)"],
        ["ChargeTarget_kW", "uint16", "0", "350", "1.0", "kW", "0"],
    ]
    story.append(make_table(dict_data, [85, 55, 40, 40, 50, 45, 130]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Signal Integrity Conventions:", h2))
    story.append(Paragraph("• All voltages are represented in millivolts (mV) to maintain integer precision on Core 0.", body))
    story.append(Paragraph("• Pack current incorporates an active zero-point offset calibrated upon every contactor open state.", body))
    story.append(PageBreak())

    # ── Page 18: Section 15 — Runnable Entities & OS Task Allocation ───────
    story.append(Paragraph("15. Runnable Entities &amp; OS Task Scheduling Allocation", h1))
    story.append(Paragraph("Runnables represent atomic units of execution invoked by the AUTOSAR OS scheduler via RTE event triggers. Execution timing budgets must never exceed 70% of task period.", body))
    story.append(Spacer(1, 0.3 * cm))

    run_data = [
        ["Runnable Entity", "Host SWC", "Trigger Event", "Period", "Budget", "Target Core"],
        ["Runnable_SafetyAudit", "SafetySupervisor", "TimingEvent", "1 ms", "120 µs", "Core 0"],
        ["Runnable_CurrentSample", "BatteryManagement", "TimingEvent", "5 ms", "350 µs", "Core 0"],
        ["Runnable_BattMonitor", "BatteryManagement", "TimingEvent", "10 ms", "850 µs", "Core 0"],
        ["Runnable_ContactorSeq", "PowerControl", "TimingEvent", "10 ms", "400 µs", "Core 1"],
        ["Runnable_ThermalControl", "ThermalManagement", "TimingEvent", "50 ms", "1.2 ms", "Core 2"],
        ["Runnable_SOC_Estimate", "BatteryManagement", "TimingEvent", "100 ms", "4.5 ms", "Core 0"],
        ["Runnable_CellBalancing", "CellBalancing", "TimingEvent", "100 ms", "1.8 ms", "Core 2"],
        ["Runnable_DcmService", "Diagnostics", "DataReceived", "Event", "2.0 ms", "Core 4"],
    ]
    story.append(make_table(run_data, [95, 80, 70, 45, 55, 100]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Scheduling Hierarchy:", h2))
    story.append(Paragraph("• Highest priority: Task_1ms (Priority 64, Non-preemptible safety loop).", body))
    story.append(Paragraph("• Medium priority: Task_10ms (Priority 48, Preemptible control loops).", body))
    story.append(Paragraph("• Background: Task_100ms (Priority 16, Telemetry and diagnostics).", body))
    story.append(PageBreak())

    # ── Page 19: Section 16 — In-Vehicle Communication Matrix (CAN FD) ────
    story.append(Paragraph("16. In-Vehicle Communication Matrix (CAN FD &amp; Ethernet)", h1))
    story.append(Paragraph("The BMS ECU interfaces with the vehicle powertrain backbone using ISO 11898-1:2015 CAN FD (500 kbps arbitration / 2.0 Mbps payload data phase) and Automotive Ethernet SOME/IP.", body))
    story.append(Spacer(1, 0.3 * cm))

    can_data = [
        ["Frame Name", "CAN ID", "Payload", "Cycle", "Transmitter", "Receiver(s)"],
        ["BMS_Status_01", "0x110", "32 bytes", "10 ms", "BMS ECU", "Inverter, VCU, Gateway"],
        ["BMS_PowerLimits", "0x112", "16 bytes", "10 ms", "BMS ECU", "Traction Inverter"],
        ["BMS_CellVoltages", "0x250", "64 bytes", "50 ms", "BMS ECU", "Instrument Cluster, VCU"],
        ["VCU_TorqueDemand", "0x090", "16 bytes", "10 ms", "VCU", "BMS, Inverter"],
        ["EVSE_ChargeParam", "0x380", "48 bytes", "100 ms", "OBC / EVSE", "BMS ChargingControl"],
    ]
    story.append(make_table(can_data, [90, 45, 60, 45, 80, 125]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Automotive Ethernet SOME/IP Services:", h2))
    story.append(Paragraph("• <b>Service ID 0x4010 (Pack Telemetry):</b> High-bandwidth stream delivering 96 individual cell voltages and 16 thermistor streams to onboard telemetry unit.", body))
    story.append(Paragraph("• <b>Service ID 0x4020 (Diagnostic Log):</b> UDS over DoIP (ISO 13400) diagnostic tunnel.", body))
    story.append(PageBreak())

    # ── Page 20: Section 17 — Non-Volatile Memory (NvM) Block Layout ───────
    story.append(Paragraph("17. Non-Volatile Memory (NvM) Block Layout", h1))
    story.append(Paragraph("Persistent operational parameters, calibration tables, and lifetime history are managed through the AUTOSAR NvM service layer with redundant CRC32 validation and wear-leveling.", body))
    story.append(Spacer(1, 0.3 * cm))

    nvm_data = [
        ["NvM Block", "Block ID", "Size", "Management Type", "CRC Type", "Description"],
        ["NvM_BMS_Calib", "0x0001", "256 B", "NATIVE", "CRC32", "Shunt resistance & ADC voltage offsets"],
        ["NvM_SOH_History", "0x0002", "512 B", "REDUNDANT", "CRC32", "Lifetime Ah throughput and cycle count"],
        ["NvM_DTC_Store", "0x0003", "1024 B", "DATASET", "CRC16", "Active and historical freeze frames"],
        ["NvM_CellBalances", "0x0004", "128 B", "NATIVE", "CRC16", "Accumulated bypass bleed timestamps"],
    ]
    story.append(make_table(nvm_data, [90, 50, 45, 85, 55, 120]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("NVRAM Recovery Strategy:", h2))
    story.append(Paragraph("Upon CRC mismatch during startup EcuM initialization, the NvM restores the default ROM calibration block and asserts a diagnostic event (DTC P0607).", body))
    story.append(PageBreak())

    # ── Page 21: Section 18 — End-to-End (E2E) Communication Protection ────
    story.append(Paragraph("18. End-to-End (E2E) Communication Protection Concept", h1))
    story.append(Paragraph("To satisfy ASIL-D functional safety requirements against communication transit faults (masquerading, insertion, corruption, and loss), critical frames implement AUTOSAR E2E Profile 01.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("E2E Header Structure:", h2))
    story.append(Paragraph("• <b>Byte 0:</b> CRC8 polynomial 0x1D (SAE J1850 standard).<br/>"
                           "• <b>Byte 1:</b> 4-bit Alive Counter (0–14) + 4-bit Data ID nibble.<br/>"
                           "• <b>Bytes 2–N:</b> Protected application payload.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Fault Tolerant Rejection Thresholds:", h3))
    story.append(Paragraph("• <b>Alive Counter Inconsistency:</b> > 2 consecutive missed increments triggers fault.", body))
    story.append(Paragraph("• <b>CRC Verification Failure:</b> 1 invalid checksum causes immediate frame discard.", body))
    story.append(Paragraph("• <b>Timeout Guard:</b> If no valid frame is received within 30 ms (3x cycle), failsafe default values are applied.", body))
    story.append(PageBreak())

    # ── Page 22: Section 19 — Vehicle Mode Management & Power States ───────
    story.append(Paragraph("19. Vehicle Mode Management &amp; Power State Machine", h1))
    story.append(Paragraph("The Vehicle Mode Manager (VMM) dictates overall BMS operational states in response to ignition key inputs, crash signals, and EVSE plug insertions.", body))
    story.append(Spacer(1, 0.3 * cm))

    mode_data = [
        ["State Name", "HV Contactors", "Active SWCs", "CAN Bus Activity", "Target Power"],
        ["STANDBY", "OPEN", "SafetySupervisor (100 ms)", "Awake / Listening", "< 0.5 W"],
        ["PRECHARGE", "PRECHARGE ON", "PowerControl, BatteryManagement", "High-speed active", "25 W"],
        ["DRIVE", "CLOSED", "All SWCs active", "Full CAN FD & Ethernet", "45 W"],
        ["CHARGING", "CLOSED", "ChargingControl, ThermalManagement", "Active EVSE loop", "35 W"],
        ["EMERGENCY", "FORCE OPEN", "SafetySupervisor, Diagnostics", "Emergency broadcasts", "10 W"],
    ]
    story.append(make_table(mode_data, [85, 75, 125, 95, 65]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Transition Constraints:", h2))
    story.append(Paragraph("• Transition from STANDBY to DRIVE requires successful insulation resistance check (> 500 kΩ).", body))
    story.append(Paragraph("• Crash signal detection transitions the system directly to EMERGENCY state within 5 ms, bypassing all ramp-down timers.", body))
    story.append(PageBreak())

    # ── Page 23: Section 20 — Cross-Component Sequences & Workflows ────────
    story.append(Paragraph("20. Cross-Component Sequences &amp; Interaction Flows", h1))
    story.append(Paragraph("This section documents the end-to-end execution sequence for primary vehicle power-up and high-voltage bus precharging.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Sequence 1: Normal Vehicle Power-On Precharge Flow", h2))
    story.append(Paragraph("1. Vehicle Control Unit transmits <code>VCU_DriveEnable</code> command over CAN FD.", body))
    story.append(Paragraph("2. <b>VehicleSafetySupervisor</b> confirms no pending ASIL-D fault flags in <b>FaultStatus_If</b>.", body))
    story.append(Paragraph("3. <b>PowerControl</b> closes the Main Negative Contactor via <code>RelayCmd_Prov</code>.", body))
    story.append(Paragraph("4. <b>PowerControl</b> engages the Precharge Contactor; current flows through the 47 ohm precharge resistor.", body))
    story.append(Paragraph("5. <b>BatteryManagement</b> samples cell string voltage while <b>InverterInterface</b> monitors DC bus rise.", body))
    story.append(Paragraph("6. When <code>V_Bus &gt;= 0.95 * V_Pack</code>, <b>PowerControl</b> closes Main Positive Contactor and opens Precharge Contactor.", body))
    story.append(Paragraph("7. <b>PowerControl</b> asserts <code>PrechargeStatus_Prov = TRUE</code>; drive authorization granted.", body))
    story.append(PageBreak())

    # ── Page 24: Section 21 — Intentional Inconsistencies & Known Issues ────
    story.append(Paragraph("21. Intentional Architectural Inconsistencies &amp; Known Issues", h1))
    story.append(Paragraph(
        "<b>Notice for Evaluators &amp; Automated Verification Engines:</b> This document contains intentionally "
        "introduced architectural inconsistencies to benchmark the AutoHLD consistency auditing and error detection pipeline.", body))
    story.append(Spacer(1, 0.3 * cm))

    incon_table = [
        ["Issue ID", "Category", "Target Component", "Page Ref", "Discrepancy Description"],
        ["INC-01", "Port Direction Mismatch", "PowerControl", "Page 10", "BattFault_Prov declared as P-Port; should be R-Port."],
        ["INC-02", "Undefined Interface", "PowerControl", "Page 10", "SafetyTrip_If interface referenced but direction ambiguous."],
        ["INC-03", "Data Type Mismatch", "BatteryManagement", "Page 8", "BattVoltage_Prov uses float32[96] while Table 14 lists uint16[96]."],
        ["INC-04", "Missing Description", "CellBalancing", "Page 11", "BalancingCmd_Prov lacks explicit timeout safety fallback."],
        ["INC-05", "Cross-Reference Conflict", "ThermalManagement", "Page 9", "AmbientTemp_Req interface VehicleEnv_If missing provider."],
    ]
    story.append(make_table(incon_table, [45, 95, 80, 50, 175]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Automated Review Expectation:", h2))
    story.append(Paragraph("AutoHLD's consistency rule checker should detect these five specific discrepancies during automated review and categorize INC-01 and INC-03 as high-priority Warnings.", body))
    story.append(PageBreak())

    # ── Page 25: Section 22–24 — Guidelines, Acceptance & Glossary ─────────
    story.append(Paragraph("22. Integration Guidelines &amp; RTE Directives", h1))
    story.append(Paragraph("When generating the AUTOSAR RTE via DaVinci Developer or EB tresos, enable <code>Rte_Read</code> and <code>Rte_Write</code> macro inlining for 1 ms tasks to minimize stack overhead.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("23. Verification &amp; Validation Criteria", h1))
    story.append(Paragraph("• <b>Model-in-the-Loop (MIL):</b> 100% statement and MC/DC coverage for ASIL-D runnables.", body))
    story.append(Paragraph("• <b>Hardware-in-the-Loop (HIL):</b> Automated testing on dSPACE SCALEXIO with high-voltage battery emulator.", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("24. Glossary of Automotive Terms", h1))

    gloss_data = [
        ["Term", "Definition"],
        ["AUTOSAR", "AUTOmotive Open System ARchitecture standard for automotive ECUs."],
        ["SWC", "Software Component — atomic functional unit in the AUTOSAR ASW."],
        ["RTE", "Runtime Environment — software middleware decoupling ASW from BSW."],
        ["P-Port", "Provided Port — communication endpoint where an SWC outputs data or services."],
        ["R-Port", "Required Port — communication endpoint where an SWC inputs data or services."],
        ["ASIL-D", "Automotive Safety Integrity Level D — highest rigor safety classification in ISO 26262."],
        ["FTTI", "Fault Tolerant Time Interval — duration between fault occurrence and hazardous event."],
        ["UDS", "Unified Diagnostic Services (ISO 14229) — standard automotive diagnostic protocol."],
    ]
    story.append(make_table(gloss_data, [80, 365]))

    # Build PDF
    doc.build(story)
    print(f"Successfully generated {OUTPUT_PATH}")
    return OUTPUT_PATH


if __name__ == "__main__":
    build_pdf()
