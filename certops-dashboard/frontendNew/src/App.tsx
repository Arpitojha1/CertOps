/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { MainLayout } from './components/layout/MainLayout';
import LandingPage from './pages/LandingPage';
import Dashboard from './pages/Dashboard';
import Certificates from './pages/Certificates';
import Connectors from './pages/Connectors';
import Activity from './pages/Activity';
import Groups from './pages/Groups';
import Notifications from './pages/Notifications';
import Scheduler from './pages/Scheduler';
import Settings from './pages/Settings';
import Profile from './pages/Profile';
import Pricing from './pages/Pricing';
import GenericPage from './pages/GenericPage';
import LoginPage from './pages/LoginPage';

// Enterprise Pages
import EntInsights from './pages/enterprise/Insights';
import EntInventory from './pages/enterprise/Inventory';
import EntActions from './pages/enterprise/Actions';
import EntDiscovery from './pages/enterprise/Discovery';
import EntHealth from './pages/enterprise/Health';
import EntPolicies from './pages/enterprise/Policies';
import EntLogs from './pages/enterprise/Logs';
import EntUpgrade from './pages/enterprise/Upgrade';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/about" element={<GenericPage title="About Us" content="Modern certificate lifecycle management. We're building the future of automated PKI." />} />
        <Route path="/careers" element={<GenericPage title="Careers" content="We're not currently hiring, but check back soon!" />} />
        <Route path="/help" element={<GenericPage title="Docs & Support" content="Welcome to the help center. How can we assist you today?" />} />
        <Route path="/privacy" element={<GenericPage title="Privacy Policy" content="Your data is your data. We don't sell it." />} />
        <Route path="/terms" element={<GenericPage title="Terms of Service" content="By using our platform, you agree to automate responsibly." />} />
        
        <Route element={<MainLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/certificates" element={<Certificates />} />
          <Route path="/connectors" element={<Connectors />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/groups" element={<Groups />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/scheduler" element={<Scheduler />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/profile" element={<Profile />} />
          
          <Route path="/enterprise">
            <Route index element={<Navigate to="insights" replace />} />
            <Route path="upgrade" element={<EntUpgrade />} />
            <Route path="insights" element={<EntInsights />} />
            <Route path="inventory" element={<EntInventory />} />
            <Route path="actions" element={<EntActions />} />
            <Route path="discovery" element={<EntDiscovery />} />
            <Route path="health" element={<EntHealth />} />
            <Route path="policies" element={<EntPolicies />} />
            <Route path="logs" element={<EntLogs />} />
          </Route>
        </Route>
        
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

