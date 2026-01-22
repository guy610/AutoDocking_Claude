"""Results panel widget for displaying patent search results.

This module provides the ResultsPanel widget that displays patent search
results with title, count, and abstract tooltip. It integrates with the
PatentSearchResponse model from the USPTO service and UnifiedPatent model
for multi-source display.

Example:
    >>> from fto_agent.widgets import ResultsPanel
    >>> panel = ResultsPanel()
    >>> panel.set_results(search_response)
    >>> panel.patentSelected.connect(on_patent_clicked)
    >>> # Or for unified multi-source results:
    >>> panel.set_unified_results(unified_patents, total_hits=100)
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from fto_agent.services.models import PatentSource, UnifiedPatent
from fto_agent.services.uspto import PatentSearchResponse


class ResultsPanel(QWidget):
    """Widget for displaying patent search results.

    Displays a list of patents with titles and abstracts (in tooltips).
    Emits patentSelected signal when user clicks a patent.

    Attributes:
        patentSelected: Signal emitted with patent_id when user clicks a patent.

    Example:
        >>> panel = ResultsPanel()
        >>> panel.set_results(response)  # Display search results
        >>> panel.patentSelected.connect(self._on_patent_selected)
    """

    patentSelected = Signal(str)  # Emitted with patent_id when clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the results panel.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Header label
        self._header_label = QLabel("Search Results")
        self._header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self._header_label)

        # Results count label
        self._count_label = QLabel("No results")
        self._count_label.setStyleSheet("color: #666;")
        layout.addWidget(self._count_label)

        # Scroll area with patent list
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Patent list widget
        self._list_widget = QListWidget()
        self._list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
        """)
        self._list_widget.itemClicked.connect(self._on_item_clicked)

        scroll_area.setWidget(self._list_widget)
        layout.addWidget(scroll_area, stretch=1)

    def set_results(self, response: PatentSearchResponse) -> None:
        """Display patent search results.

        Updates the count label and populates the list with patent titles.
        Each item shows the title and has the abstract as a tooltip.

        Args:
            response: PatentSearchResponse from USPTO search.
        """
        # Update count label
        if response.total_hits > 0:
            self._count_label.setText(
                f"Found {response.total_hits} patents (showing {response.count})"
            )
            self._count_label.setStyleSheet("color: #2e7d32;")  # Green for results
        else:
            self._count_label.setText("No patents found matching your query")
            self._count_label.setStyleSheet("color: #666;")

        # Clear existing items
        self._list_widget.clear()

        # Add patent items
        for patent in response.patents:
            item = QListWidgetItem(patent.patent_title)

            # Build tooltip with abstract
            tooltip_parts = [f"Patent: {patent.patent_id}"]
            if patent.patent_date:
                tooltip_parts.append(f"Date: {patent.patent_date}")
            if patent.patent_abstract:
                # Truncate abstract to 300 chars
                abstract = patent.patent_abstract
                if len(abstract) > 300:
                    abstract = abstract[:297] + "..."
                tooltip_parts.append(f"\n{abstract}")

            item.setToolTip("\n".join(tooltip_parts))

            # Store patent_id for retrieval on click
            item.setData(Qt.ItemDataRole.UserRole, patent.patent_id)

            self._list_widget.addItem(item)

        # Re-enable list
        self._list_widget.setEnabled(True)

    def set_loading(self, loading: bool) -> None:
        """Set the loading state.

        Args:
            loading: True to show loading state, False to enable list.
        """
        if loading:
            self._count_label.setText("Searching...")
            self._count_label.setStyleSheet("color: #1976d2;")  # Blue for loading
            self._list_widget.setEnabled(False)
        else:
            self._list_widget.setEnabled(True)

    def set_error(self, message: str) -> None:
        """Display an error message.

        Args:
            message: Error message to display.
        """
        self._count_label.setText(f"Error: {message}")
        self._count_label.setStyleSheet("color: #c62828;")  # Red for error
        self._list_widget.clear()
        self._list_widget.setEnabled(True)

    def clear(self) -> None:
        """Reset to initial state."""
        self._count_label.setText("No results")
        self._count_label.setStyleSheet("color: #666;")
        self._list_widget.clear()
        self._list_widget.setEnabled(True)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle patent item click.

        Args:
            item: The clicked list item.
        """
        patent_id = item.data(Qt.ItemDataRole.UserRole)
        if patent_id:
            self.patentSelected.emit(patent_id)

    def set_unified_results(
        self, patents: list[UnifiedPatent], total_hits: int | None = None
    ) -> None:
        """Display unified patents from multiple sources.

        Updates the count label and populates the list with patent titles
        from multiple sources (USPTO, EPO). Each patent shows a source indicator
        prefix like [USPTO] or [EPO].

        Args:
            patents: List of UnifiedPatent objects.
            total_hits: Total matching patents (optional, for status display).
        """
        # Calculate sources for count label
        sources = set(p.source for p in patents)
        count = len(patents)
        hits = total_hits if total_hits is not None else count

        # Update count label with source info
        if count > 0:
            source_str = f"from {len(sources)} source{'s' if len(sources) > 1 else ''}"
            self._count_label.setText(f"Found {hits} patents {source_str}")
            self._count_label.setStyleSheet("color: #2e7d32;")  # Green for results
        else:
            self._count_label.setText("No patents found matching your query")
            self._count_label.setStyleSheet("color: #666;")

        # Clear existing items
        self._list_widget.clear()

        # Add patent items with source indicators
        for patent in patents:
            source_indicator = self._format_source_indicator(patent.source)
            item = QListWidgetItem(f"{source_indicator} {patent.title}")

            # Build tooltip with id, date, abstract, and source
            tooltip_parts = [f"Patent: {patent.id}"]
            tooltip_parts.append(f"Source: {patent.source.value}")
            if patent.date:
                tooltip_parts.append(f"Date: {patent.date}")
            if patent.abstract:
                # Truncate abstract to 300 chars
                abstract = patent.abstract
                if len(abstract) > 300:
                    abstract = abstract[:297] + "..."
                tooltip_parts.append(f"\n{abstract}")

            item.setToolTip("\n".join(tooltip_parts))

            # Store patent.id for retrieval on click
            item.setData(Qt.ItemDataRole.UserRole, patent.id)

            # Color-code by source (optional: USPTO blue, EPO green)
            if patent.source == PatentSource.USPTO:
                item.setForeground(QColor("#1565c0"))  # Blue for USPTO
            elif patent.source == PatentSource.EPO:
                item.setForeground(QColor("#2e7d32"))  # Green for EPO

            self._list_widget.addItem(item)

        # Re-enable list
        self._list_widget.setEnabled(True)

    def _format_source_indicator(self, source: PatentSource) -> str:
        """Format source indicator for display.

        Args:
            source: PatentSource enum value.

        Returns:
            Formatted string like "[USPTO]" or "[EPO]".
        """
        return f"[{source.value}]"
