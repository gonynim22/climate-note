"""환산기의 짧은 기준 표시와 접는 조건 입력. 저장/DB 접근 없음."""
import math

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from unit_converter import BASIS_SUMMARIES, CATEGORY_BY_ID, ConversionConditions, GASES, format_number, parse_number
from ui_converter_combo import ConverterCombo


def condition_summary(category_id, conditions):
    if category_id == "water":
        mode = "물 기준 ≈" if conditions.water_approximation else "직접 입력"
        density = format_number(conditions.density_kg_l) if conditions.density_kg_l is not None else "—"
        return f"{mode} · 밀도 {density} kg/L"
    if category_id == "temp":
        return "온도차 · 증가/감소량" if conditions.temperature_difference else "온도값 · 절대영도 이상"
    if category_id == "gas_fraction":
        if conditions.molar_mass is None:
            return "몰분율 기준"
        gas = GASES.get(conditions.gas_id)
        name = gas[0].split(" · ")[-1] if gas else f"M {format_number(conditions.molar_mass)} g/mol"
        temp = format_number(conditions.temperature_c) if conditions.temperature_c is not None else "—"
        pressure = format_number(conditions.pressure_kpa) if conditions.pressure_kpa is not None else "—"
        return f"{name} · 이상기체 근사\n{temp}°C · {pressure} kPa 절대압"
    return BASIS_SUMMARIES.get(category_id, "선택한 단위의 정의 기준")


class ConversionConditionsPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.category_id = "len"
        self._updating = False
        self.water_approximation = True
        self._mass_selected = False
        self.setStyleSheet("""
            QLabel { color:#527166; font-size:11px; }
            QLineEdit { background:#FFFFFF; color:#292C33; border:1px solid #CDD5DA; border-radius:4px; padding:3px 5px; font-size:13px; }
            QLineEdit:focus { border-color:#46679C; }
            QPushButton, QToolButton { color:#46679C; background:transparent; border:1px solid #CDD5DA; border-radius:4px; padding:3px 6px; font-size:11px; }
            QPushButton:hover, QPushButton:focus, QToolButton:hover, QToolButton:focus { background:#EAF0F5; border-color:#46679C; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 5)
        layout.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(4)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        top.addWidget(self.summary, 1)
        self.toggle = QToolButton()
        self.toggle.setText("기준 ⓘ")
        self.toggle.setAccessibleName("환산 기준과 조건 펼치기")
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self._toggle_details)
        top.addWidget(self.toggle)
        layout.addLayout(top)
        self.temperature_mode = ConverterCombo()
        self.temperature_mode.setAccessibleName("온도값 또는 온도차")
        self.temperature_mode.addItems(["온도값", "온도차 (증가·감소량)"])
        layout.addWidget(self.temperature_mode)
        self.gas_picker = ConverterCombo()
        self.gas_picker.setAccessibleName("환산할 기체 물질")
        self.gas_picker.addItem("물질 선택…", "")
        for gas_id, (label, _) in GASES.items():
            self.gas_picker.addItem(label, gas_id)
        self.gas_picker.addItem("몰질량 직접 입력", "custom")
        layout.addWidget(self.gas_picker)
        self.molar_mass_input = self._input("", "몰질량 (g/mol)")
        self.mass_row = self._field("몰질량", self.molar_mass_input, "g/mol")
        layout.addWidget(self.mass_row)
        self.details = QWidget()
        detail_layout = QVBoxLayout(self.details)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(4)
        self.density_input = self._input("1", "용액 밀도 (kg/L)")
        self.density_row = self._field("용액 밀도", self.density_input, "kg/L")
        detail_layout.addWidget(self.density_row)
        self.gas_temperature_input = self._input("25", "기체 온도 (섭씨)")
        self.temperature_row = self._field("온도", self.gas_temperature_input, "°C")
        detail_layout.addWidget(self.temperature_row)
        self.gas_pressure_input = self._input("101.325", "기체 절대압 (kPa)")
        self.pressure_row = self._field("절대압", self.gas_pressure_input, "kPa")
        detail_layout.addWidget(self.pressure_row)
        self.reset_button = QPushButton()
        self.reset_button.clicked.connect(self._reset_conditions)
        detail_layout.addWidget(self.reset_button)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        detail_layout.addWidget(self.note)
        layout.addWidget(self.details)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.error.setStyleSheet("color:#BB4040;font-size:11px;")
        layout.addWidget(self.error)
        self.temperature_mode.currentIndexChanged.connect(self._changed)
        self.gas_picker.currentIndexChanged.connect(self._changed)
        self.density_input.textEdited.connect(self._density_edited)
        for edit in (self.density_input, self.molar_mass_input, self.gas_temperature_input, self.gas_pressure_input):
            edit.textChanged.connect(self._changed)
        self.set_category("len")

    @staticmethod
    def _input(text, name):
        edit = QLineEdit(text)
        edit.setMaxLength(96)
        edit.setMinimumWidth(45)
        edit.setAccessibleName(name)
        return edit

    @staticmethod
    def _field(label, edit, unit):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        caption = QLabel(label)
        caption.setBuddy(edit)
        layout.addWidget(caption)
        layout.addWidget(edit, 1)
        layout.addWidget(QLabel(unit))
        return row

    def _density_edited(self):
        self.water_approximation = False
        self._changed()

    def _toggle_details(self, expanded):
        self.details.setVisible(expanded)
        self.toggle.setAccessibleName("환산 기준과 조건 접기" if expanded else "환산 기준과 조건 펼치기")
        self._refresh()

    def set_category(self, category_id):
        self.category_id = category_id
        self.toggle.setChecked(False)
        self._mass_selected = False
        self._refresh()

    def set_units(self, from_id, to_id):
        category = CATEGORY_BY_ID[self.category_id]
        self._mass_selected = self.category_id == "gas_fraction" and any(
            category.unit(uid).kind == "mass_concentration" for uid in (from_id, to_id))
        self._refresh()

    def _refresh(self):
        self.details.setVisible(self.toggle.isChecked())
        water, gas, temp = (self.category_id == cid for cid in ("water", "gas_fraction", "temp"))
        self.toggle.setText("밀도 ▾" if water else "조건 ▾" if gas else "기준 ⓘ")
        self.temperature_mode.setVisible(temp)
        gas_controls = gas and (self._mass_selected or self.toggle.isChecked())
        self.gas_picker.setVisible(gas_controls)
        self.mass_row.setVisible(gas_controls and self.gas_picker.currentData() == "custom")
        self.density_row.setVisible(water)
        self.temperature_row.setVisible(gas)
        self.pressure_row.setVisible(gas)
        self.reset_button.setVisible(water or gas)
        self.reset_button.setText("물 기준 복원" if water else "25°C · 1기압 복원")
        category = CATEGORY_BY_ID[self.category_id]
        self.note.setText(category.note or BASIS_SUMMARIES.get(self.category_id, "선택한 단위끼리 고정 배율로 환산합니다."))
        try:
            self.summary.setText(condition_summary(self.category_id, self.conditions()))
            self.error.clear()
        except ValueError as exc:
            self.summary.setText("조건 입력 확인")
            self.error.setText(str(exc))
        self.error.setVisible(bool(self.error.text()))

    def _changed(self, *_):
        if not self._updating:
            self._refresh()
            self.changed.emit()

    def _reset_conditions(self):
        self._updating = True
        if self.category_id == "water":
            self.density_input.setText("1")
            self.water_approximation = True
        else:
            self.gas_temperature_input.setText("25")
            self.gas_pressure_input.setText("101.325")
        self._updating = False
        self._changed()

    @staticmethod
    def _number(edit, label, *, positive=False, minimum=None, optional=False):
        value = parse_number(edit.text())
        if value is None and optional:
            return None
        if value is None:
            raise ValueError(f"{label}을 입력하세요.")
        if not math.isfinite(value) or (positive and value <= 0) or (minimum is not None and value <= minimum):
            raise ValueError(f"{label}은 0보다 커야 합니다." if positive else f"{label}은 {minimum}보다 커야 합니다.")
        return value

    def conditions(self):
        if self.category_id == "water":
            return ConversionConditions(density_kg_l=self._number(self.density_input, "용액 밀도", positive=True),
                                        water_approximation=self.water_approximation)
        if self.category_id == "temp":
            return ConversionConditions(temperature_difference=self.temperature_mode.currentIndex() == 1)
        if self.category_id == "gas_fraction":
            gas_id = self.gas_picker.currentData()
            mass = GASES[gas_id][1] if gas_id in GASES else None
            if gas_id == "custom":
                mass = self._number(self.molar_mass_input, "몰질량", positive=True)
            return ConversionConditions(molar_mass=mass, gas_id=gas_id,
                temperature_c=self._number(self.gas_temperature_input, "기체 온도", minimum=-273.15),
                pressure_kpa=self._number(self.gas_pressure_input, "절대압", positive=True))
        return ConversionConditions()

    def restore(self, conditions):
        self._updating = True
        try:
            if self.category_id == "water":
                self.density_input.setText(repr(conditions.density_kg_l))
                self.water_approximation = conditions.water_approximation
            elif self.category_id == "temp":
                self.temperature_mode.setCurrentIndex(int(conditions.temperature_difference))
            elif self.category_id == "gas_fraction":
                self.gas_picker.setCurrentIndex(max(0, self.gas_picker.findData(conditions.gas_id)))
                self.molar_mass_input.setText("" if conditions.molar_mass is None else repr(conditions.molar_mass))
                self.gas_temperature_input.setText(repr(conditions.temperature_c))
                self.gas_pressure_input.setText(repr(conditions.pressure_kpa))
        finally:
            self._updating = False
        self._refresh()
