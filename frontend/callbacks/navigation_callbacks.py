"""
CORRIGIDO
Callbacks para navegação entre páginas e controle de roteamento.

Features:
- Navegação entre Home, ETo, Documentação e Sobre
- Redirecionamento para página ETo com localização
- Controle de estado da navbar
- Integração com sistema de localização
"""

import logging

from dash import callback_context, html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from ..pages.home import home_layout
from ..pages.dash_eto import eto_layout
from ..pages.about import about_layout
from ..pages.documentation import documentation_layout

logger = logging.getLogger(__name__)


def register_navigation_callbacks(app):
    """
    Registra todos os callbacks relacionados à navegação
    """

    # Navigation callback - Roteamento básico
    @app.callback(
        Output("page-content", "children"), [Input("url", "pathname")]
    )
    def display_page(pathname):
        """
        Controla a exibição das páginas baseado na URL.
        """
        logger.info(f"🧭 Navegando para: {pathname}")
        pages = {
            "/eto-calculator": eto_layout,  # ✅ Rota principal
            "/about": about_layout,
            "/documentation": documentation_layout,
        }
        return pages.get(pathname, home_layout)

    # Navigation callback - Link direto navbar para ETo (sem coordenadas)
    @app.callback(
        Output("url", "pathname", allow_duplicate=True),
        Input("nav-eto", "n_clicks"),
        prevent_initial_call=True,
    )
    def navigate_to_eto_from_navbar(n_clicks):
        """
        Navega para ETo calculator via navbar (SEM coordenadas).
        Callbacks específicos (botão Home) preservam coordenadas via Store.
        """
        if n_clicks:
            logger.info("� Navegando para ETo (navbar)")
            return "/eto-calculator"
        raise PreventUpdate

    # Navigation callback - Navbar links (EXCETO nav-eto que tem callback próprio)
    @app.callback(
        Output("url", "pathname", allow_duplicate=True),
        [
            Input("nav-home", "n_clicks"),
            Input("nav-documentation", "n_clicks"),
            Input("nav-about", "n_clicks"),
        ],
        prevent_initial_call=True,
    )
    def handle_navbar_navigation(home_clicks, doc_clicks, about_clicks):
        """
        Manipula navegação pela navbar (EXCETO nav-eto).
        nav-eto é controlado por callbacks específicos que preservam query params.
        """
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]["prop_id"]

        if "nav-home" in trigger_id and home_clicks:
            logger.info("🏠 Navegando para Home")
            return "/"
        elif "nav-documentation" in trigger_id and doc_clicks:
            logger.info("📚 Navegando para Documentação")
            return "/documentation"
        elif "nav-about" in trigger_id and about_clicks:
            logger.info("ℹ️ Navegando para Sobre")
            return "/about"

        raise PreventUpdate

    # Navigation callback - Toggle navbar em mobile
    @app.callback(
        Output("navbar-collapse", "is_open"),
        [Input("navbar-toggler", "n_clicks")],
        [State("navbar-collapse", "is_open")],
    )
    def toggle_navbar(n_clicks, is_open):
        """
        Alterna a navbar em dispositivos móveis
        """
        if n_clicks:
            logger.debug("📱 Alternando estado da navbar")
            return not is_open
        return is_open

    # Navigation callback - Atualiza links ativos na navbar
    @app.callback(
        [
            Output("nav-home", "active"),
            Output("nav-eto", "active"),
            Output("nav-documentation", "active"),
            Output("nav-about", "active"),
        ],
        [Input("url", "pathname")],
    )
    def update_navbar_active_links(pathname):
        """
        Atualiza os links ativos na navbar baseado na página atual
        """
        if pathname == "/eto-calculator":
            return False, True, False, False
        elif pathname == "/documentation":
            return False, False, True, False
        elif pathname == "/about":
            return False, False, False, True
        else:  # Home ou qualquer outra página
            return True, False, False, False

    # Clientside callback para atualizar título da página (sem duplicação)
    app.clientside_callback(
        """
        function(pathname) {
            const titles = {
                '/': 'EVAonline: Home',
                '/eto-calculator': 'EVAonline: Calcular ETo',
                '/documentation': 'EVAonline: Documentação',
                '/about': 'EVAonline: Sobre'
            };
            document.title = titles[pathname] || 'EVAonline';
            return '';
        }
        """,
        Output("url", "search"),  # Output dummy (não usado)
        Input("url", "pathname"),
    )

    # Navigation callback - Simula loading entre páginas
    @app.callback(
        Output("page-loading", "children"), [Input("url", "pathname")]
    )
    def handle_page_loading(pathname):
        """
        Simula loading entre páginas (pode ser usado para mostrar spinner)
        """
        logger.info(f"🔄 Carregando página: {pathname}")
        return html.Div()  # Pode ser extendido para mostrar loading spinner

    # Final do registro de callbacks
    logger.info("✅ Callbacks de navegação registrados com sucesso")
