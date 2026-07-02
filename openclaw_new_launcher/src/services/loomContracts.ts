export type {
  AccountSnapshot,
  AccountSubscriptionSnapshot,
  AgentModelConfigStatus,
  BridgeJob,
  ComponentSnapshot,
  ComponentSummary,
  DiagnosticCheck,
  DiagnosticReport,
  DiagnosticStatus,
  MatrixDeviceSummary,
  MatrixEvent,
  MatrixStatusSnapshot,
  PhoneConfigSnapshot,
  PhoneDeviceSummary,
  PhoneTaskMode,
  PhoneTaskProfile,
  WireSnapshot,
} from './api';

export interface LoomBackendError {
  ok?: false;
  code?: string;
  message: string;
  detail?: unknown;
  action?: string;
}
