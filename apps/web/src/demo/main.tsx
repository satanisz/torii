import React from 'react';
import ReactDOM from 'react-dom/client';
import { DemoApp } from './DemoApp';
import '../styles.css';
import './demo.css';

const root = document.getElementById('root');
if (!root) throw new Error('Missing application root');
ReactDOM.createRoot(root).render(<React.StrictMode><DemoApp /></React.StrictMode>);
