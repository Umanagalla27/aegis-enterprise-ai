from dataclasses import dataclass


@dataclass
class ExtractedDiagram:
    diagram_id: str
    caption: str
    extracted_text: str
    page: int


class MultimodalRunbookParser:
    """Parses infrastructure diagrams and tables from PDF runbooks."""

    def parse_mock_diagram(self, page_num: int = 1) -> ExtractedDiagram:
        return ExtractedDiagram(
            diagram_id="DIAG-ARCH-01",
            caption="High-Availability Kubernetes Pod Topology and Ingress Flow",
            extracted_text="Ingress -> ALB -> Envoy Sidecar -> FastAPI Service -> RDS Multi-AZ",
            page=page_num,
        )
