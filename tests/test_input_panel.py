"""Unit tests for InputPanel widget.

Tests verify the InputPanel widget including:
- Widget creation and initial state
- Form validity checking
- Data collection
- SMILES validation visual feedback
- Signal emission
- Clear functionality

Uses pytest-qt for Qt widget testing.
"""

import pytest
from PySide6.QtCore import Qt

from fto_agent.widgets import InputPanel


class TestInputPanelCreation:
    """Tests for InputPanel widget creation."""

    def test_input_panel_creation(self, qtbot):
        """InputPanel can be created without error."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        assert panel is not None

    def test_input_panel_has_required_widgets(self, qtbot):
        """InputPanel has all required input widgets."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Check all expected widgets exist
        assert hasattr(panel, "problem_edit")
        assert hasattr(panel, "solution_edit")
        assert hasattr(panel, "constraints_edit")
        assert hasattr(panel, "smiles_edit")
        assert hasattr(panel, "smiles_status")
        assert hasattr(panel, "country_checks")
        assert hasattr(panel, "submit_button")

    def test_input_panel_initial_validity(self, qtbot):
        """Empty form is invalid (required fields not filled)."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Fresh panel should be invalid
        assert panel.is_valid() is False
        assert panel.submit_button.isEnabled() is False

    def test_input_panel_countries_default_checked(self, qtbot):
        """All countries are checked by default."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # All country checkboxes should be checked
        for code, checkbox in panel.country_checks.items():
            assert checkbox.isChecked() is True, f"Country {code} should be checked"


class TestInputPanelValidity:
    """Tests for InputPanel form validation."""

    def test_input_panel_validity_with_required_fields(self, qtbot):
        """Form is valid when problem, solution filled and country selected."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Fill required fields
        panel.problem_edit.setPlainText("Test problem description")
        panel.solution_edit.setPlainText("Test solution description")
        # Countries are checked by default

        # Form should now be valid
        assert panel.is_valid() is True
        assert panel.submit_button.isEnabled() is True

    def test_input_panel_validity_without_countries(self, qtbot):
        """Form is invalid when no countries are selected."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Fill text fields
        panel.problem_edit.setPlainText("Test problem")
        panel.solution_edit.setPlainText("Test solution")

        # Uncheck all countries
        for checkbox in panel.country_checks.values():
            checkbox.setChecked(False)

        # Form should be invalid
        assert panel.is_valid() is False
        assert panel.submit_button.isEnabled() is False

    def test_input_panel_validity_without_problem(self, qtbot):
        """Form is invalid when problem field is empty."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Fill only solution
        panel.solution_edit.setPlainText("Test solution")

        assert panel.is_valid() is False

    def test_input_panel_validity_without_solution(self, qtbot):
        """Form is invalid when solution field is empty."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Fill only problem
        panel.problem_edit.setPlainText("Test problem")

        assert panel.is_valid() is False

    def test_input_panel_validity_with_invalid_smiles(self, qtbot):
        """Form is invalid when SMILES is provided but invalid."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Fill required fields
        panel.problem_edit.setPlainText("Test problem")
        panel.solution_edit.setPlainText("Test solution")

        # Enter invalid SMILES
        panel.smiles_edit.setText("invalid_smiles_xyz")

        # Form should be invalid due to invalid SMILES
        assert panel.is_valid() is False

    def test_input_panel_validity_with_valid_smiles(self, qtbot):
        """Form is valid when all required fields filled and SMILES is valid."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Fill required fields
        panel.problem_edit.setPlainText("Test problem")
        panel.solution_edit.setPlainText("Test solution")

        # Enter valid SMILES (ethanol)
        panel.smiles_edit.setText("CCO")

        # Form should be valid
        assert panel.is_valid() is True


class TestInputPanelGetData:
    """Tests for InputPanel data collection."""

    def test_input_panel_get_data_keys(self, qtbot):
        """get_data() returns dict with all expected keys."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        data = panel.get_data()

        expected_keys = {"problem", "solution", "constraints", "smiles", "countries"}
        assert set(data.keys()) == expected_keys

    def test_input_panel_get_data_values(self, qtbot):
        """Values in get_data() match what was entered."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Set specific values
        panel.problem_edit.setPlainText("My problem description")
        panel.solution_edit.setPlainText("My solution description")
        panel.constraints_edit.setPlainText("My constraints")
        panel.smiles_edit.setText("CCO")

        # Uncheck some countries
        panel.country_checks["CN"].setChecked(False)
        panel.country_checks["JP"].setChecked(False)

        data = panel.get_data()

        assert data["problem"] == "My problem description"
        assert data["solution"] == "My solution description"
        assert data["constraints"] == "My constraints"
        assert data["smiles"] == "CCO"
        assert set(data["countries"]) == {"US", "EU"}

    def test_input_panel_get_data_empty_optional_fields(self, qtbot):
        """Empty optional fields return None."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Leave constraints and smiles empty
        panel.problem_edit.setPlainText("Problem")
        panel.solution_edit.setPlainText("Solution")

        data = panel.get_data()

        assert data["constraints"] is None
        assert data["smiles"] is None

    def test_input_panel_get_data_whitespace_stripped(self, qtbot):
        """Whitespace is stripped from text fields."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Enter text with extra whitespace
        panel.problem_edit.setPlainText("  Problem with spaces  ")
        panel.solution_edit.setPlainText("\n\tSolution\n")
        panel.smiles_edit.setText("  CCO  ")

        data = panel.get_data()

        assert data["problem"] == "Problem with spaces"
        assert data["solution"] == "Solution"
        assert data["smiles"] == "CCO"


class TestInputPanelSmilesValidation:
    """Tests for SMILES validation visual feedback."""

    def test_input_panel_smiles_validation_valid(self, qtbot):
        """Valid SMILES shows green feedback."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Enter valid SMILES
        panel.smiles_edit.setText("CCO")

        # Check status shows valid
        assert "Valid" in panel.smiles_status.text()
        # Check validation property
        assert panel.smiles_edit.property("validationState") == "valid"

    def test_input_panel_smiles_validation_invalid(self, qtbot):
        """Invalid SMILES shows red feedback."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Enter invalid SMILES
        panel.smiles_edit.setText("invalid")

        # Check status shows invalid
        assert "Invalid" in panel.smiles_status.text()
        # Check validation property
        assert panel.smiles_edit.property("validationState") == "error"

    def test_input_panel_smiles_validation_empty(self, qtbot):
        """Empty SMILES clears validation feedback."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Enter then clear SMILES
        panel.smiles_edit.setText("CCO")
        panel.smiles_edit.setText("")

        # Status should be empty
        assert panel.smiles_status.text() == ""
        assert panel.smiles_edit.property("validationState") == ""


class TestInputPanelClear:
    """Tests for InputPanel clear functionality."""

    def test_input_panel_clear(self, qtbot):
        """clear() resets all fields to default state."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Fill all fields
        panel.problem_edit.setPlainText("Problem")
        panel.solution_edit.setPlainText("Solution")
        panel.constraints_edit.setPlainText("Constraints")
        panel.smiles_edit.setText("CCO")

        # Uncheck some countries
        panel.country_checks["US"].setChecked(False)
        panel.country_checks["EU"].setChecked(False)

        # Clear the panel
        panel.clear()

        # Verify all fields are cleared
        assert panel.problem_edit.toPlainText() == ""
        assert panel.solution_edit.toPlainText() == ""
        assert panel.constraints_edit.toPlainText() == ""
        assert panel.smiles_edit.text() == ""

        # Verify all countries are checked again
        for checkbox in panel.country_checks.values():
            assert checkbox.isChecked() is True


class TestInputPanelSignals:
    """Tests for InputPanel signal emission."""

    def test_input_panel_submit_signal(self, qtbot):
        """submitRequested signal emitted when submit button clicked."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Make form valid first
        panel.problem_edit.setPlainText("Problem")
        panel.solution_edit.setPlainText("Solution")

        # Set up signal spy
        with qtbot.waitSignal(panel.submitRequested, timeout=1000) as blocker:
            panel.submit_button.click()

        # Signal should have been emitted
        assert blocker.signal_triggered

    def test_input_panel_validity_changed_signal_on_valid(self, qtbot):
        """validityChanged signal emitted when form becomes valid."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Monitor validity changes
        validity_values = []
        panel.validityChanged.connect(lambda v: validity_values.append(v))

        # Fill required fields to make valid
        panel.problem_edit.setPlainText("Problem")
        panel.solution_edit.setPlainText("Solution")

        # Should have emitted True at some point
        assert True in validity_values

    def test_input_panel_validity_changed_signal_on_invalid(self, qtbot):
        """validityChanged signal emitted when form becomes invalid."""
        panel = InputPanel()
        qtbot.addWidget(panel)

        # First make valid
        panel.problem_edit.setPlainText("Problem")
        panel.solution_edit.setPlainText("Solution")

        # Monitor validity changes
        validity_values = []
        panel.validityChanged.connect(lambda v: validity_values.append(v))

        # Make invalid by clearing required field
        panel.problem_edit.setPlainText("")

        # Should have emitted False
        assert False in validity_values
