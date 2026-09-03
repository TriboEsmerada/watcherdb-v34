#!/usr/bin/env python3
"""Add new i18n keys (pluralization, interpolation, etc.) to existing JSON files."""
import json
import os

BASE = os.path.join(os.path.dirname(__file__), '..', 'static', 'i18n')

NEW_KEYS = {
    'pt': {
        'plural': {
            'results': '{count} resultado|{count} resultados',
            'items': '{count} item|{count} itens',
            'servers': '{count} servidor|{count} servidores',
            'instances': '{count} instancia|{count} instancias',
            'databases': '{count} database|{count} databases',
            'users_count': '{count} usuario|{count} usuarios',
            'sessions': '{count} sessao|{count} sessoes',
            'alerts': '{count} alerta|{count} alertas',
            'issues': '{count} problema|{count} problemas',
            'days': '{count} dia|{count} dias',
            'hours': '{count} hora|{count} horas',
            'minutes': '{count} minuto|{count} minutos',
            'records': '{count} registo|{count} registos',
            'jobs_count': '{count} job|{count} jobs',
            'checks': '{count} verificacao|{count} verificacoes',
            'events': '{count} evento|{count} eventos'
        },
        'interp': {
            'welcome': 'Bem-vindo, {name}',
            'last_update': 'Ultima atualizacao: {time}',
            'showing_of': 'Mostrando {count} de {total}',
            'page_of': 'Pagina {page} de {total}',
            'server_name': 'Servidor: {name}',
            'instance_name': 'Instancia: {name}',
            'environment_name': 'Ambiente: {env}',
            'data_from': 'Dados de {time}',
            'cached_ago': 'Cache de {minutes} min atras',
            'error_detail': 'Erro: {message}',
            'confirm_delete': 'Tem certeza que deseja eliminar "{name}"?',
            'connected_to': 'Conectado a {server}',
            'n_of_total': '{n} de {total}'
        },
        'confirm': {
            'delete_title': 'Confirmar Exclusao',
            'delete_message': 'Esta acao nao pode ser desfeita.',
            'yes_delete': 'Sim, Eliminar',
            'no_cancel': 'Nao, Cancelar',
            'save_changes': 'Guardar alteracoes?',
            'discard_changes': 'Descartar alteracoes?'
        },
        'success': {
            'saved': 'Configuracoes guardadas com sucesso',
            'exported': 'Exportacao concluida com sucesso',
            'copied': 'Copiado para a area de transferencia',
            'refreshed': 'Dados atualizados com sucesso',
            'connected': 'Conexao estabelecida com sucesso'
        },
        'error': {
            'generic': 'Ocorreu um erro inesperado',
            'connection': 'Erro de conexao com o servidor',
            'timeout_detail': 'A requisicao excedeu o tempo limite de {seconds}s',
            'not_found': 'Recurso nao encontrado',
            'permission': 'Sem permissao para esta acao',
            'validation': 'Dados invalidos. Verifique os campos.',
            'server_unreachable': 'Servidor inacessivel'
        },
        'nav': {
            'home': 'Inicio',
            'server_details': 'Detalhes do Servidor',
            'back_to_dashboard': 'Voltar ao Dashboard',
            'back_to_list': 'Voltar a lista'
        },
        'a11y': {
            'lang_selector': 'Selecionar idioma',
            'close_modal': 'Fechar janela',
            'open_menu': 'Abrir menu',
            'expand_section': 'Expandir secao',
            'collapse_section': 'Recolher secao',
            'sort_asc': 'Ordenar ascendente',
            'sort_desc': 'Ordenar descendente',
            'loading_content': 'Conteudo a carregar'
        }
    },
    'en': {
        'plural': {
            'results': '{count} result|{count} results',
            'items': '{count} item|{count} items',
            'servers': '{count} server|{count} servers',
            'instances': '{count} instance|{count} instances',
            'databases': '{count} database|{count} databases',
            'users_count': '{count} user|{count} users',
            'sessions': '{count} session|{count} sessions',
            'alerts': '{count} alert|{count} alerts',
            'issues': '{count} issue|{count} issues',
            'days': '{count} day|{count} days',
            'hours': '{count} hour|{count} hours',
            'minutes': '{count} minute|{count} minutes',
            'records': '{count} record|{count} records',
            'jobs_count': '{count} job|{count} jobs',
            'checks': '{count} check|{count} checks',
            'events': '{count} event|{count} events'
        },
        'interp': {
            'welcome': 'Welcome, {name}',
            'last_update': 'Last update: {time}',
            'showing_of': 'Showing {count} of {total}',
            'page_of': 'Page {page} of {total}',
            'server_name': 'Server: {name}',
            'instance_name': 'Instance: {name}',
            'environment_name': 'Environment: {env}',
            'data_from': 'Data from {time}',
            'cached_ago': 'Cached {minutes} min ago',
            'error_detail': 'Error: {message}',
            'confirm_delete': 'Are you sure you want to delete "{name}"?',
            'connected_to': 'Connected to {server}',
            'n_of_total': '{n} of {total}'
        },
        'confirm': {
            'delete_title': 'Confirm Deletion',
            'delete_message': 'This action cannot be undone.',
            'yes_delete': 'Yes, Delete',
            'no_cancel': 'No, Cancel',
            'save_changes': 'Save changes?',
            'discard_changes': 'Discard changes?'
        },
        'success': {
            'saved': 'Settings saved successfully',
            'exported': 'Export completed successfully',
            'copied': 'Copied to clipboard',
            'refreshed': 'Data refreshed successfully',
            'connected': 'Connection established successfully'
        },
        'error': {
            'generic': 'An unexpected error occurred',
            'connection': 'Server connection error',
            'timeout_detail': 'Request timed out after {seconds}s',
            'not_found': 'Resource not found',
            'permission': 'Permission denied for this action',
            'validation': 'Invalid data. Please check the fields.',
            'server_unreachable': 'Server unreachable'
        },
        'nav': {
            'home': 'Home',
            'server_details': 'Server Details',
            'back_to_dashboard': 'Back to Dashboard',
            'back_to_list': 'Back to list'
        },
        'a11y': {
            'lang_selector': 'Select language',
            'close_modal': 'Close window',
            'open_menu': 'Open menu',
            'expand_section': 'Expand section',
            'collapse_section': 'Collapse section',
            'sort_asc': 'Sort ascending',
            'sort_desc': 'Sort descending',
            'loading_content': 'Loading content'
        }
    },
    'es': {
        'plural': {
            'results': '{count} resultado|{count} resultados',
            'items': '{count} elemento|{count} elementos',
            'servers': '{count} servidor|{count} servidores',
            'instances': '{count} instancia|{count} instancias',
            'databases': '{count} base de datos|{count} bases de datos',
            'users_count': '{count} usuario|{count} usuarios',
            'sessions': '{count} sesion|{count} sesiones',
            'alerts': '{count} alerta|{count} alertas',
            'issues': '{count} problema|{count} problemas',
            'days': '{count} dia|{count} dias',
            'hours': '{count} hora|{count} horas',
            'minutes': '{count} minuto|{count} minutos',
            'records': '{count} registro|{count} registros',
            'jobs_count': '{count} job|{count} jobs',
            'checks': '{count} verificacion|{count} verificaciones',
            'events': '{count} evento|{count} eventos'
        },
        'interp': {
            'welcome': 'Bienvenido, {name}',
            'last_update': 'Ultima actualizacion: {time}',
            'showing_of': 'Mostrando {count} de {total}',
            'page_of': 'Pagina {page} de {total}',
            'server_name': 'Servidor: {name}',
            'instance_name': 'Instancia: {name}',
            'environment_name': 'Entorno: {env}',
            'data_from': 'Datos de {time}',
            'cached_ago': 'Cache de hace {minutes} min',
            'error_detail': 'Error: {message}',
            'confirm_delete': 'Esta seguro de que desea eliminar "{name}"?',
            'connected_to': 'Conectado a {server}',
            'n_of_total': '{n} de {total}'
        },
        'confirm': {
            'delete_title': 'Confirmar Eliminacion',
            'delete_message': 'Esta accion no se puede deshacer.',
            'yes_delete': 'Si, Eliminar',
            'no_cancel': 'No, Cancelar',
            'save_changes': 'Guardar cambios?',
            'discard_changes': 'Descartar cambios?'
        },
        'success': {
            'saved': 'Configuracion guardada con exito',
            'exported': 'Exportacion completada con exito',
            'copied': 'Copiado al portapapeles',
            'refreshed': 'Datos actualizados con exito',
            'connected': 'Conexion establecida con exito'
        },
        'error': {
            'generic': 'Ocurrio un error inesperado',
            'connection': 'Error de conexion con el servidor',
            'timeout_detail': 'La solicitud supero el tiempo limite de {seconds}s',
            'not_found': 'Recurso no encontrado',
            'permission': 'Sin permiso para esta accion',
            'validation': 'Datos invalidos. Verifique los campos.',
            'server_unreachable': 'Servidor inaccesible'
        },
        'nav': {
            'home': 'Inicio',
            'server_details': 'Detalles del Servidor',
            'back_to_dashboard': 'Volver al Dashboard',
            'back_to_list': 'Volver a la lista'
        },
        'a11y': {
            'lang_selector': 'Seleccionar idioma',
            'close_modal': 'Cerrar ventana',
            'open_menu': 'Abrir menu',
            'expand_section': 'Expandir seccion',
            'collapse_section': 'Contraer seccion',
            'sort_asc': 'Ordenar ascendente',
            'sort_desc': 'Ordenar descendente',
            'loading_content': 'Cargando contenido'
        }
    }
}


def count_keys(d):
    """Count total leaf keys in a nested dict."""
    n = 0
    for v in d.values():
        if isinstance(v, dict):
            n += count_keys(v)
        else:
            n += 1
    return n


def deep_merge(base, overlay):
    """Merge overlay into base recursively."""
    for k, v in overlay.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            deep_merge(base[k], v)
        else:
            base[k] = v


for lang in ['pt', 'en', 'es']:
    path = os.path.join(BASE, f'{lang}.json')
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    deep_merge(data, NEW_KEYS[lang])

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)

    total = count_keys(data)
    print(f'{lang}.json: {total} total keys')


print('Done!')
