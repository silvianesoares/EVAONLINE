"""
Navbar profissional para ETO Calculator - Bootstrap Materia + Cores ESALQ.
Inclui logo, links internos + extras (GitHub, Licença, Contato).
"""

import dash_bootstrap_components as dbc
from dash import html


def create_navbar():
    """
    Cria navbar responsiva com logo e links.
    Returns:
        dbc.Navbar: Navbar completa.
    """
    navbar = dbc.Navbar(
        [
            # Logo + Brand (esquerda)
            html.Div(
                [
                    html.A(
                        [
                            html.Img(
                                src="/assets/images/logo_evaonline.svg",
                                alt="ETO Calculator Logo",
                                height="40",
                                className="me-2",
                            ),
                            html.Span(
                                "ETO Calculator", className="navbar-brand mb-0"
                            ),
                        ],
                        href="/",  # Home
                        style={"textDecoration": "none"},
                    ),
                ],
                className="navbar-brand",
            ),
            # Toggle para mobile (collapse)
            dbc.NavbarToggler(id="navbar-toggler"),
            # Links principais (direita)
            dbc.Collapse(
                dbc.Nav(
                    [
                        # Links internos (pages/)
                        dbc.NavItem(
                            dbc.NavLink(
                                "Home",
                                href="/",
                                id="nav-home",
                                className="nav-link-custom",
                            )
                        ),
                        dbc.NavItem(
                            dbc.NavLink(
                                "Calcular ETo",
                                href="/eto-calculator",
                                id="nav-eto",
                                className="nav-link-custom",
                            )
                        ),
                        dbc.NavItem(
                            dbc.NavLink(
                                "Documentação",
                                href="/documentation",
                                id="nav-documentation",
                                className="nav-link-custom",
                            )
                        ),
                        dbc.NavItem(
                            dbc.NavLink(
                                "Sobre",
                                href="/about",
                                id="nav-about",
                                className="nav-link-custom",
                            )
                        ),
                        # Divider (visual)
                        dbc.NavItem(
                            html.Div("|", className="mx-2 text-white-50")
                        ),
                        # Links extras (profissional)
                        dbc.NavItem(
                            dbc.NavLink(
                                "GitHub Repo",
                                href="https://github.com/angelacunhasoares/EVAonline_SoftwareX",
                                target="_blank",
                                className="nav-link-custom",
                            )
                        ),
                        dbc.NavItem(
                            dbc.NavLink(
                                "Licença",
                                href="https://github.com/angelacunhasoares/EVAonline_SoftwareX?tab=License-1-ov-file",
                                target="_blank",
                                className="nav-link-custom",
                            )
                        ),
                        dbc.NavItem(
                            dbc.NavLink(
                                "Contato",
                                href="mailto:angelacunhasoares@usp.br",  # Ou /contact para form futuro
                                className="nav-link-custom",
                            )
                        ),
                    ],
                    className="ms-auto",
                    navbar=True,
                ),
                id="navbar-collapse",
                navbar=True,
            ),
        ],
        color="dark",  # Fundo escuro (Materia verde-escuro via CSS)
        dark=True,
        className="navbar-expand-lg",  # Expande em lg (992px+)
        style={
            "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",  # Sombra sutil (Materia style)
        },
    )

    # Callback para toggle (Bootstrap auto, mas confirme)
    return navbar
