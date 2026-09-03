/**
 * WatcherDB Frontend Type Definitions
 */

// i18n
declare function t(key: string): string;
declare function tCategory(name: string): string;
declare function setLanguage(lang: 'pt' | 'en' | 'es'): void;

// Security
declare function safeHTML(element: HTMLElement, html: string): void;

// DOMPurify
declare const DOMPurify: {
    sanitize(dirty: string, config?: Record<string, any>): string;
};

// MaintenanceScore
declare const MaintenanceScore: {
    init(): void;
    showDetails(instance: string, score: number): void;
};

// ChaosDetection
declare const ChaosDetection: {
    init(): void;
};

// DBACopilot
declare const DBACopilot: {
    init(): void;
    askQuestion(question: string): void;
    generateReport(type: string): void;
};

// WatcherDB API types
interface ServerHealth {
    server_name: string;
    instance_name: string;
    environment: string;
    status: string;
    health_score: number;
    alerts_count: number;
}

interface KPIDashboard {
    summary: Record<string, any>;
    servers: ServerHealth[];
    categories: Record<string, any>;
}

interface CopilotAnswer {
    answer: string;
    recommendations?: string[];
}

interface CopilotInsight {
    severity: string;
    title: string;
    description: string;
    suggested_action: string;
}
